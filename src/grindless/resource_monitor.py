from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResourceMeasurement:
    wall_time_seconds: float
    peak_python_rss_bytes: int
    peak_process_tree_rss_bytes: int
    sampling_interval_ms: int
    samples: int
    complete: bool
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "wall_time_seconds": round(self.wall_time_seconds, 3),
            "peak_python_rss_bytes": self.peak_python_rss_bytes,
            "peak_process_tree_rss_bytes": self.peak_process_tree_rss_bytes,
            "sampling_interval_ms": self.sampling_interval_ms,
            "samples": self.samples,
            "complete": self.complete,
            "warnings": list(self.warnings),
            "memory_metric": "sampled sum of RSS for Python and descendant processes",
        }


class ProcessTreeProfiler:
    """Sample wall time and the current process tree's resident memory."""

    def __init__(
        self,
        *,
        sampling_interval_ms: int = 100,
        psutil_module: Any = None,
    ) -> None:
        if sampling_interval_ms <= 0:
            raise ValueError("sampling_interval_ms must be positive")
        self.sampling_interval_ms = sampling_interval_ms
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._root: Any = None
        self._psutil: Any = psutil_module
        self._started_at: float | None = None
        self._peak_python_rss_bytes = 0
        self._peak_process_tree_rss_bytes = 0
        self._samples = 0
        self._complete = True
        self._warnings: set[str] = set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("process-tree profiler has already started")
        if self._psutil is None:
            try:
                import psutil
            except ImportError as exc:
                raise RuntimeError(
                    "process-tree measurement requires the browser dependencies; "
                    "install grindless-agent[browser]"
                ) from exc
            self._psutil = psutil

        self._root = self._psutil.Process(os.getpid())
        try:
            same_executable = os.path.samefile(self._root.exe(), sys.executable)
        except (OSError, self._psutil.AccessDenied):
            same_executable = False
        if not same_executable:
            raise RuntimeError(
                "process-tree measurement cannot identify the current Python process"
            )
        self._started_at = time.perf_counter()
        self._sample()
        self._thread = threading.Thread(
            target=self._sample_until_stopped,
            name="grindless-resource-profiler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> ResourceMeasurement:
        if self._started_at is None or self._thread is None:
            raise RuntimeError("process-tree profiler has not started")
        self._stop_event.set()
        self._thread.join(timeout=max(1.0, self.sampling_interval_ms / 250.0))
        if self._thread.is_alive():
            self._complete = False
            self._warnings.add("memory sampler did not stop cleanly")
        self._sample()
        elapsed = time.perf_counter() - self._started_at
        return ResourceMeasurement(
            wall_time_seconds=elapsed,
            peak_python_rss_bytes=self._peak_python_rss_bytes,
            peak_process_tree_rss_bytes=self._peak_process_tree_rss_bytes,
            sampling_interval_ms=self.sampling_interval_ms,
            samples=self._samples,
            complete=self._complete,
            warnings=tuple(sorted(self._warnings)),
        )

    def _sample_until_stopped(self) -> None:
        interval_seconds = self.sampling_interval_ms / 1000.0
        while not self._stop_event.wait(interval_seconds):
            self._sample()

    def _sample(self) -> None:
        try:
            python_rss = self._root.memory_info().rss
        except (self._psutil.NoSuchProcess, self._psutil.ZombieProcess):
            self._complete = False
            self._warnings.add("Python process disappeared during memory sampling")
            return
        except self._psutil.AccessDenied:
            self._complete = False
            self._warnings.add("Python RSS was inaccessible during memory sampling")
            return

        tree_rss = python_rss
        try:
            children = self._root.children(recursive=True)
        except (self._psutil.NoSuchProcess, self._psutil.ZombieProcess):
            children = []
        except self._psutil.AccessDenied:
            children = []
            self._complete = False
            self._warnings.add("child process list was partially inaccessible")

        for child in children:
            try:
                tree_rss += child.memory_info().rss
            except (self._psutil.NoSuchProcess, self._psutil.ZombieProcess):
                continue
            except self._psutil.AccessDenied:
                self._complete = False
                self._warnings.add("a child process RSS was inaccessible")

        self._samples += 1
        self._peak_python_rss_bytes = max(self._peak_python_rss_bytes, python_rss)
        self._peak_process_tree_rss_bytes = max(
            self._peak_process_tree_rss_bytes, tree_rss
        )
