from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol

from pydantic import BaseModel

from .artiscan_browser import ArtiscanBrowserConfig, BrowserArtiscanExtractor
from .good_import import import_good
from .inventory_input import VIDEO_SUFFIXES


class GoodExtractor(Protocol):
    last_audit: object | None

    def extract_good(self, video_path: Path) -> dict[str, object]: ...


class VideoImportView(BaseModel):
    job_id: str
    status: Literal["queued", "scanning", "succeeded", "failed"]
    filename: str
    created_at: str
    updated_at: str
    phase: str
    progress: float | None = None
    message: str
    good: dict[str, object] | None = None
    extraction_audit: dict[str, object] | None = None
    error: str | None = None


@dataclass
class _Job:
    job_id: str
    filename: str
    created_at: str
    updated_at: str
    directory: Path
    video_path: Path
    status: Literal["queued", "scanning", "succeeded", "failed"] = "queued"
    phase: str = "queued"
    progress: float | None = None
    message: str = "Видео принято. Подготавливаем локальный Artiscan."
    good: dict[str, object] | None = None
    extraction_audit: dict[str, object] | None = None
    error: str | None = None
    lock: Lock = field(default_factory=Lock)


class VideoImportBusyError(RuntimeError):
    pass


class VideoImportService:
    """Single-user background boundary for automatic local video imports."""

    def __init__(
        self,
        data_directory: Path,
        *,
        extractor_factory: Callable[[], GoodExtractor] | None = None,
    ) -> None:
        profile = data_directory / "artiscan-browser-profile"
        self._extractor_factory = extractor_factory or (
            lambda: BrowserArtiscanExtractor(
                ArtiscanBrowserConfig(headless=True, profile_directory=profile)
            )
        )
        self._jobs: dict[str, _Job] = {}
        self._jobs_lock = Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="grindless-artiscan"
        )

    def create_upload(self, filename: str) -> tuple[str, Path]:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or suffix not in VIDEO_SUFFIXES:
            raise ValueError("поддерживаются видео MP4, MOV, MKV и WebM")
        with self._jobs_lock:
            if any(job.status in {"queued", "scanning"} for job in self._jobs.values()):
                raise VideoImportBusyError(
                    "уже выполняется другой видеоскан; завершите его перед новым импортом"
                )
            self._jobs = {
                old_id: job
                for old_id, job in self._jobs.items()
                if job.status in {"queued", "scanning"}
            }
            job_id = uuid.uuid4().hex
            directory = Path(tempfile.mkdtemp(prefix="grindless-video-"))
            video_path = directory / f"inventory{suffix}"
            self._jobs[job_id] = _Job(
                job_id=job_id,
                filename=safe_name,
                created_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                directory=directory,
                video_path=video_path,
            )
        return job_id, video_path

    def start(self, job_id: str) -> None:
        job = self._job(job_id)
        if not job.video_path.is_file():
            self.discard(job_id)
            raise ValueError("временный видеофайл не был сохранён")
        self._executor.submit(self._run, job)

    def discard(self, job_id: str) -> None:
        with self._jobs_lock:
            job = self._jobs.pop(job_id, None)
        if job is not None:
            shutil.rmtree(job.directory, ignore_errors=True)

    def get(self, job_id: str) -> VideoImportView:
        job = self._job(job_id)
        with job.lock:
            return VideoImportView(
                job_id=job.job_id,
                status=job.status,
                filename=job.filename,
                created_at=job.created_at,
                updated_at=job.updated_at,
                phase=job.phase,
                progress=job.progress,
                message=job.message,
                good=job.good,
                extraction_audit=job.extraction_audit,
                error=job.error,
            )

    def _job(self, job_id: str) -> _Job:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def _run(self, job: _Job) -> None:
        with job.lock:
            job.status = "scanning"
            job.phase = "starting"
            job.updated_at = datetime.now(UTC).isoformat()
            job.message = (
                "Artiscan локально распознаёт видео: No выбирается автоматически, "
                "а чёрный хвост останавливается без ручного клика."
            )
        try:
            extractor = self._extractor_factory()
            set_progress = getattr(extractor, "set_progress_callback", None)
            if callable(set_progress):
                set_progress(
                    lambda phase, message, progress: self._report_progress(
                        job, phase, message, progress
                    )
                )
            payload = extractor.extract_good(job.video_path)
            inventory = import_good(payload)
            if not inventory.artifacts:
                raise ValueError("Artiscan не распознал ни одного артефакта")
            audit = getattr(extractor, "last_audit", None)
            audit_payload = audit.as_dict() if hasattr(audit, "as_dict") else None
            with job.lock:
                job.good = payload
                job.extraction_audit = audit_payload
                job.status = "succeeded"
                job.phase = "succeeded"
                job.progress = 1
                job.updated_at = datetime.now(UTC).isoformat()
                job.message = (
                    f"Распознано и проверено: {len(inventory.artifacts)} артефактов."
                )
        except Exception as exc:  # noqa: BLE001 - worker must expose scanner failures
            with job.lock:
                failed_phase = job.phase
                job.status = "failed"
                job.phase = "failed"
                job.updated_at = datetime.now(UTC).isoformat()
                job.error = str(exc)
                job.message = (
                    f"Ошибка на этапе {failed_phase}: {exc}. "
                    "Частичный результат не импортирован."
                )
        finally:
            try:
                job.video_path.unlink(missing_ok=True)
                job.directory.rmdir()
            except OSError:
                shutil.rmtree(job.directory, ignore_errors=True)

    @staticmethod
    def _report_progress(
        job: _Job,
        phase: str,
        message: str,
        progress: float | None,
    ) -> None:
        with job.lock:
            job.phase = phase
            job.message = message
            job.progress = progress
            job.updated_at = datetime.now(UTC).isoformat()
