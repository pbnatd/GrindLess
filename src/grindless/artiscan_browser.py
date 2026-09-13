from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlparse

from .resource_monitor import ProcessTreeProfiler, ResourceMeasurement

ARTISCAN_ORIGIN = "https://artiscan.ninjabay.org"
ARTISCAN_ROUTE = f"{ARTISCAN_ORIGIN}/#/gi-artifacts"
PINNED_ARTISCAN_BUILD = "2026-08-11 21:06:10"
TRANSCODING_PROMPT = "Would you like to transcode the video?"

SCAN_STATE_PROBE = r"""({ stallTimeoutMs, nearEndIdleMs }) => {
    const catalogueMatch = document.body.innerText.match(
      /You have ([0-9]+) artifact\(s\) catalogued\./
    );
    const cataloguedCount = catalogueMatch
      ? Number.parseInt(catalogueMatch[1], 10)
      : 0;
    const catalogued = cataloguedCount > 0;
    const dialog = [...document.querySelectorAll('dialog[open]')]
      .find(item => item.innerText.includes('Running Scan'));
    if (!dialog) {
      const previousState = window.__grindlessScanEndState;
      const stalled = previousState &&
        performance.now() - previousState.lastActivityAt >= stallTimeoutMs;
      return {
        event: catalogued ? 'artiscan_completed' : stalled ? 'stalled' : 'waiting',
        progress: catalogued ? 1 : null,
      };
    }

    const stopButtons = [...dialog.querySelectorAll('button')]
      .filter(item => item.textContent.trim() === 'Stop Scan');
    if (stopButtons.length !== 1) {
      return { event: 'ambiguous_stop', progress: null };
    }

    const state = window.__grindlessScanEndState ||= {
      seenContent: false,
      blackSince: null,
      lastActivityAt: performance.now(),
      lastCataloguedCount: cataloguedCount,
      lastProgress: null,
      lastSignature: null,
    };
    if (state.lastCataloguedCount !== cataloguedCount) {
      state.lastCataloguedCount = cataloguedCount;
      state.lastActivityAt = performance.now();
    }

    const classifyIdle = progress => {
      const idleMs = performance.now() - state.lastActivityAt;
      const nearEndIdle = progress !== null && progress >= 0.985 &&
        cataloguedCount > 0 && idleMs >= nearEndIdleMs;
      const stalled = idleMs >= stallTimeoutMs;
      return {
        event: nearEndIdle ? 'near_end_idle' : stalled ? 'stalled' : 'running',
        progress,
        cataloguedCount,
        idleMs,
      };
    };

    const progressWidths = [...dialog.querySelectorAll('[style]')]
      .map(item => item.style.width)
      .filter(value => /^([0-9]+(?:\.[0-9]+)?)%$/.test(value))
      .map(value => Number.parseFloat(value));
    const remainingPercent = progressWidths.length === 1
      ? progressWidths[0]
      : null;
    const progress = remainingPercent === null
      ? null
      : Math.max(0, Math.min(1, 1 - remainingPercent / 100));
    if (progress !== null && (
      state.lastProgress === null || Math.abs(progress - state.lastProgress) >= 0.001
    )) {
      state.lastProgress = progress;
      state.lastActivityAt = performance.now();
    }

    const canvases = [...dialog.querySelectorAll('canvas')]
      .filter(canvas => {
        const rect = canvas.getBoundingClientRect();
        const style = getComputedStyle(canvas);
        return canvas.width > 0 && canvas.height > 0 &&
          rect.width > 0 && rect.height > 0 &&
          style.visibility !== 'hidden' && style.display !== 'none';
      })
      .sort((left, right) => {
        const a = left.getBoundingClientRect();
        const b = right.getBoundingClientRect();
        return b.width * b.height - a.width * a.height;
      });
    const sourceCanvas = canvases[0];
    if (!sourceCanvas) {
      return classifyIdle(progress);
    }

    const canvas = state.canvas ||= document.createElement('canvas');
    canvas.width = 32;
    canvas.height = 18;
    const context = state.context ||= canvas.getContext('2d', {
      alpha: false,
      willReadFrequently: true,
    });
    if (!context) {
      return classifyIdle(progress);
    }

    try {
      context.drawImage(sourceCanvas, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let darkPixels = 0;
      let luminanceSum = 0;
      let signature = 2166136261;
      const pixelCount = pixels.length / 4;
      for (let index = 0; index < pixels.length; index += 4) {
        const red = pixels[index];
        const green = pixels[index + 1];
        const blue = pixels[index + 2];
        const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
        luminanceSum += luminance;
        if (red <= 24 && green <= 24 && blue <= 24) {
          darkPixels += 1;
        }
        signature ^= (red >> 4) | ((green >> 4) << 4) | ((blue >> 4) << 8);
        signature = Math.imul(signature, 16777619);
      }
      if (state.lastSignature !== signature) {
        state.lastSignature = signature;
        state.lastActivityAt = performance.now();
      }
      const isBlack = darkPixels / pixelCount >= 0.98 &&
        luminanceSum / pixelCount <= 12;
      if (!isBlack) {
        state.seenContent = true;
        state.blackSince = null;
      } else if (state.seenContent && (progress === null || progress >= 0.8)) {
        state.blackSince ??= performance.now();
        if (performance.now() - state.blackSince >= 750) {
          return { event: 'black_tail', progress, cataloguedCount, idleMs: 0 };
        }
      }

      return classifyIdle(progress);
    } catch (_error) {
      return classifyIdle(progress);
    }
  }"""

ArtiscanProgressCallback = Callable[[str, str, float | None], None]


class ArtiscanBrowserError(RuntimeError):
    """Safe-stop error raised by the experimental browser adapter."""


@dataclass(frozen=True)
class NetworkDecision:
    method: str
    url: str
    resource_type: str
    allowed: bool
    reason: str


@dataclass
class ArtiscanExtractionAudit:
    site_build: str | None = None
    browser_was_offline_before_video: bool = False
    artifacts_exported: int = 0
    network: list[NetworkDecision] = field(default_factory=list)
    performance: ResourceMeasurement | None = None
    interaction_mode: str = "unknown"
    manual_checkpoints: list[str] = field(default_factory=list)
    automated_actions: list[str] = field(default_factory=list)
    scan_stop_trigger: str | None = None
    scan_stop_control: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "site_build": self.site_build,
            "browser_was_offline_before_video": self.browser_was_offline_before_video,
            "artifacts_exported": self.artifacts_exported,
            "interaction_mode": self.interaction_mode,
            "manual_checkpoints": list(self.manual_checkpoints),
            "automated_actions": list(self.automated_actions),
            "scan_stop_trigger": self.scan_stop_trigger,
            "scan_stop_control": self.scan_stop_control,
            "performance": (
                self.performance.as_dict() if self.performance is not None else None
            ),
            "network": [
                {
                    "method": item.method,
                    "url": item.url,
                    "resource_type": item.resource_type,
                    "allowed": item.allowed,
                    "reason": item.reason,
                }
                for item in self.network
            ],
        }


@dataclass(frozen=True)
class ArtiscanBrowserConfig:
    origin: str = ARTISCAN_ORIGIN
    route: str = ARTISCAN_ROUTE
    expected_build: str = PINNED_ARTISCAN_BUILD
    headless: bool = True
    profile_directory: Path | None = None
    timeout_ms: int = 8 * 60 * 1000
    stall_timeout_ms: int = 90 * 1000
    near_end_idle_ms: int = 10 * 1000
    progress_callback: ArtiscanProgressCallback | None = field(
        default=None, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise ValueError("Artiscan timeout must be positive")
        if self.stall_timeout_ms <= 0:
            raise ValueError("Artiscan stall timeout must be positive")
        if self.near_end_idle_ms <= 0:
            raise ValueError("Artiscan near-end idle timeout must be positive")
        if self.near_end_idle_ms >= self.stall_timeout_ms:
            raise ValueError(
                "Artiscan near-end idle timeout must be shorter than stall timeout"
            )
        parsed = urlparse(self.origin)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Artiscan origin must be an absolute HTTPS origin")
        route = urlparse(self.route)
        if (route.scheme, route.netloc) != (parsed.scheme, parsed.netloc):
            raise ValueError("Artiscan route must use the configured origin")


class ArtiscanSessionRunner(Protocol):
    def run(
        self, video_path: Path, config: ArtiscanBrowserConfig
    ) -> tuple[dict[str, Any], ArtiscanExtractionAudit]: ...


@dataclass(frozen=True)
class ScanStopOutcome:
    trigger: str
    control: str | None


class ArtiscanNetworkPolicy:
    """Allow only static same-origin GETs before the browser goes offline."""

    def __init__(self, origin: str = ARTISCAN_ORIGIN) -> None:
        parsed = urlparse(origin)
        self._scheme = parsed.scheme
        self._netloc = parsed.netloc

    def decide(self, method: str, url: str, resource_type: str) -> NetworkDecision:
        normalized_method = method.upper()
        parsed = urlparse(url)
        if resource_type == "websocket":
            return NetworkDecision(
                normalized_method, url, resource_type, False, "websocket blocked"
            )
        if normalized_method != "GET":
            return NetworkDecision(
                normalized_method, url, resource_type, False, "non-GET blocked"
            )
        if parsed.scheme in {"blob", "data", "about"}:
            return NetworkDecision(
                normalized_method, url, resource_type, True, "local browser URL"
            )
        if (parsed.scheme, parsed.netloc) != (self._scheme, self._netloc):
            return NetworkDecision(
                normalized_method, url, resource_type, False, "foreign origin blocked"
            )
        return NetworkDecision(
            normalized_method, url, resource_type, True, "same-origin static GET"
        )


class BrowserArtiscanExtractor:
    """Experimental local video-to-GOOD adapter for the Artiscan PWA."""

    def __init__(
        self,
        config: ArtiscanBrowserConfig | None = None,
        *,
        runner: ArtiscanSessionRunner | None = None,
        profiler_factory: Callable[[], ProcessTreeProfiler] = ProcessTreeProfiler,
    ) -> None:
        self.config = config or ArtiscanBrowserConfig()
        self._runner = runner or PlaywrightArtiscanSession()
        self._profiler_factory = profiler_factory
        self.last_audit: ArtiscanExtractionAudit | None = None
        self.last_good: dict[str, object] | None = None

    def set_progress_callback(
        self, callback: ArtiscanProgressCallback | None
    ) -> None:
        self.config = replace(self.config, progress_callback=callback)

    def extract_good(self, video_path: Path) -> dict[str, object]:
        self.last_audit = None
        self.last_good = None
        path = video_path.expanduser().resolve()
        if not path.is_file():
            raise ArtiscanBrowserError(f"video file does not exist: {path}")
        if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
            raise ArtiscanBrowserError(f"unsupported video type: {path.suffix}")

        profiler = self._profiler_factory()
        try:
            profiler.start()
        except RuntimeError as exc:
            raise ArtiscanBrowserError(str(exc)) from exc

        try:
            payload, audit = self._runner.run(path, self.config)
        finally:
            performance = profiler.stop()
        audit.performance = performance
        self.last_audit = audit
        if payload.get("format") != "GOOD":
            raise ArtiscanBrowserError("Artiscan export is not a GOOD document")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ArtiscanBrowserError("Artiscan exported zero artifacts")
        audit.artifacts_exported = len(artifacts)
        self.last_good = payload
        return payload


class PlaywrightArtiscanSession:
    """Playwright implementation kept optional and imported only when selected."""

    def run(
        self, video_path: Path, config: ArtiscanBrowserConfig
    ) -> tuple[dict[str, Any], ArtiscanExtractionAudit]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ArtiscanBrowserError(
                "Artiscan browser extraction needs the optional 'browser' dependencies"
            ) from exc

        audit = ArtiscanExtractionAudit(
            interaction_mode="fully_automated",
        )
        policy = ArtiscanNetworkPolicy(config.origin)
        profile = config.profile_directory
        temporary_profile: TemporaryDirectory[str] | None = None
        if profile is None:
            temporary_profile = TemporaryDirectory(prefix="grindless-artiscan-")
            profile = Path(temporary_profile.name)
        profile.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as playwright:
                try:
                    context = playwright.chromium.launch_persistent_context(
                        str(profile),
                        headless=config.headless,
                        accept_downloads=True,
                        service_workers="allow",
                    )
                except Exception as exc:
                    raise ArtiscanBrowserError(
                        "Chromium could not start; install the Playwright Chromium browser"
                    ) from exc

                def enforce_route(route: Any) -> None:
                    request = route.request
                    decision = policy.decide(
                        request.method, request.url, request.resource_type
                    )
                    audit.network.append(decision)
                    if decision.allowed:
                        route.continue_()
                    else:
                        route.abort("blockedbyclient")

                context.route("**/*", enforce_route)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    self._notify(
                        config,
                        "opening",
                        "Открываем проверенную версию Artiscan.",
                        None,
                    )
                    self._open_scanner(page, config, PlaywrightTimeoutError)
                    audit.site_build = self._read_and_verify_build(page, config)

                    context.set_offline(True)
                    audit.browser_was_offline_before_video = True
                    self._notify(
                        config,
                        "loading_video",
                        "Artiscan локально разбирает видеофайл.",
                        None,
                    )
                    page.locator('input[accept="video/*"]').set_input_files(
                        str(video_path)
                    )
                    transcode_prompt = self._decline_transcoding(
                        page, config, PlaywrightTimeoutError
                    )
                    audit.automated_actions.append(
                        "decline_video_transcoding"
                        if transcode_prompt == "declined"
                        else "transcoding_prompt_not_present"
                    )
                    self._wait_for_source(page, config, PlaywrightTimeoutError)
                    self._notify(
                        config,
                        "configuring",
                        "Проверяем область распознавания артефактов.",
                        None,
                    )
                    self._ensure_configuration(page, config, PlaywrightTimeoutError)
                    stop_outcome = self._run_scan(
                        page, config, PlaywrightTimeoutError
                    )
                    audit.scan_stop_trigger = stop_outcome.trigger
                    audit.scan_stop_control = stop_outcome.control
                    if audit.scan_stop_trigger == "black_tail":
                        audit.automated_actions.append("stop_scan_at_black_tail")
                    elif audit.scan_stop_trigger == "near_end_idle":
                        audit.automated_actions.append("stop_scan_after_near_end_idle")
                    if stop_outcome.control == "artifact_correction":
                        audit.automated_actions.append(
                            "stop_scan_in_artifact_correction"
                        )
                    self._notify(
                        config,
                        "exporting",
                        "Скан завершён. Получаем и проверяем GOOD JSON.",
                        1,
                    )
                    payload = self._download_good(page, config, PlaywrightTimeoutError)
                    return payload, audit
                finally:
                    context.close()
        finally:
            if temporary_profile is not None:
                temporary_profile.cleanup()

    @staticmethod
    def _notify(
        config: ArtiscanBrowserConfig,
        phase: str,
        message: str,
        progress: float | None,
    ) -> None:
        if config.progress_callback is not None:
            config.progress_callback(phase, message, progress)

    @staticmethod
    def _open_scanner(page: Any, config: ArtiscanBrowserConfig, timeout: type) -> None:
        page.goto(
            config.route, wait_until="domcontentloaded", timeout=config.timeout_ms
        )
        video_input = page.locator('input[accept="video/*"]')
        try:
            video_input.wait_for(
                state="attached", timeout=min(config.timeout_ms, 120_000)
            )
        except timeout:
            # The first visit installs Artiscan's service worker but does not mount
            # the application until the next load.
            page.reload(wait_until="domcontentloaded", timeout=config.timeout_ms)
            try:
                video_input.wait_for(
                    state="attached", timeout=min(config.timeout_ms, 120_000)
                )
            except timeout as exc:
                raise ArtiscanBrowserError(
                    "Artiscan scanner UI did not reach the expected state"
                ) from exc

    @staticmethod
    def _read_and_verify_build(page: Any, config: ArtiscanBrowserConfig) -> str:
        text = page.locator("body").inner_text(timeout=config.timeout_ms)
        match = re.search(r"Build:\s*([^\n]+)", text)
        if match is None:
            raise ArtiscanBrowserError("Artiscan build identifier was not found")
        observed = match.group(1).strip()
        if observed != config.expected_build:
            raise ArtiscanBrowserError(
                "Artiscan build changed: "
                f"expected {config.expected_build!r}, observed {observed!r}"
            )
        return observed

    @staticmethod
    def _decline_transcoding(
        page: Any, config: ArtiscanBrowserConfig, timeout: type
    ) -> str:
        prompt = page.get_by_text(TRANSCODING_PROMPT, exact=True)
        try:
            prompt.wait_for(state="visible", timeout=min(config.timeout_ms, 30_000))
        except timeout as exc:
            # Artiscan can legitimately reuse the previously chosen no-transcode
            # preference and proceed directly to Configure. Treat that state as
            # success only when the next pinned control is already visible.
            configure = page.get_by_role("button", name="Configure", exact=True)
            try:
                configure.wait_for(
                    state="visible", timeout=min(config.timeout_ms, 30_000)
                )
            except timeout as configure_exc:
                raise ArtiscanBrowserError(
                    "Artiscan showed neither the transcoding choice nor the Configure step"
                ) from configure_exc
            return "not_present"
        no_button = page.get_by_role("button", name="No", exact=True)
        try:
            no_button.wait_for(state="visible", timeout=min(config.timeout_ms, 30_000))
        except timeout as exc:
            raise ArtiscanBrowserError(
                "Artiscan transcoding prompt has no pinned No action"
            ) from exc
        if prompt.count() != 1 or no_button.count() != 1:
            raise ArtiscanBrowserError(
                "Artiscan transcoding prompt is ambiguous; refusing to guess a button"
            )
        no_button.click()
        try:
            prompt.wait_for(state="hidden", timeout=30_000)
        except timeout as exc:
            raise ArtiscanBrowserError(
                "Artiscan did not accept the automated No transcoding choice"
            ) from exc
        return "declined"

    @staticmethod
    def _wait_for_source(
        page: Any, config: ArtiscanBrowserConfig, timeout: type
    ) -> None:
        configure = page.get_by_role("button", name="Configure", exact=True)
        try:
            configure.wait_for(state="visible", timeout=config.timeout_ms)
            page.wait_for_function(
                """() => {
                    const button = [...document.querySelectorAll('button')]
                      .find(item => item.textContent.trim() === 'Configure');
                    return button && !button.disabled;
                }""",
                timeout=config.timeout_ms,
            )
        except timeout as exc:
            raise ArtiscanBrowserError(
                "Artiscan could not decode the selected video source"
            ) from exc

    @staticmethod
    def _ensure_configuration(
        page: Any, config: ArtiscanBrowserConfig, timeout: type
    ) -> None:
        body = page.locator("body").inner_text(timeout=config.timeout_ms)
        needs_configuration = any(
            marker in body
            for marker in (
                "Artifact scanner has not been configured yet.",
                "Configure the scanner first.",
                "Source is not compatible with the current configuration.",
            )
        )
        if not needs_configuration:
            return

        page.get_by_role("button", name="Configure", exact=True).click()
        try:
            page.get_by_role("button", name="Artifact Inventory", exact=True).click(
                timeout=30_000
            )
            page.get_by_role("button", name="Auto-detect", exact=True).click(
                timeout=30_000
            )
            setup_confirm = page.get_by_role("button", name="Confirm", exact=True).last
            page.wait_for_function(
                """() => {
                    const buttons = [...document.querySelectorAll('button')]
                      .filter(item => item.textContent.trim() === 'Confirm');
                    const button = buttons.at(-1);
                    return button && !button.disabled;
                }""",
                timeout=60_000,
            )
            setup_confirm.click()
            config_confirm = page.get_by_role("button", name="Confirm", exact=True).last
            page.wait_for_function(
                """() => {
                    const buttons = [...document.querySelectorAll('button')]
                      .filter(item => item.textContent.trim() === 'Confirm');
                    const button = buttons.at(-1);
                    return button && !button.disabled;
                }""",
                timeout=30_000,
            )
            config_confirm.click()
        except timeout as exc:
            mode = "visible" if not config.headless else "headless"
            raise ArtiscanBrowserError(
                "Artiscan auto-configuration failed in "
                f"{mode} mode; use a clear 1080p-or-higher English inventory video"
            ) from exc

    @staticmethod
    def _run_scan(
        page: Any, config: ArtiscanBrowserConfig, timeout: type
    ) -> ScanStopOutcome:
        try:
            page.evaluate("delete window.__grindlessScanEndState")
            page.get_by_role("button", name="Start Scan", exact=True).click(
                timeout=30_000
            )
            page.wait_for_function(
                """() => [...document.querySelectorAll('dialog[open]')]
                  .filter(item => item.innerText.includes('Running Scan')).length === 1""",
                timeout=30_000,
            )
            open_dialogs = page.locator('dialog[open]')
            running_dialog = open_dialogs.filter(has_text="Running Scan")
            if running_dialog.count() != 1:
                raise ArtiscanBrowserError(
                    "Artiscan Running Scan dialog is unavailable or ambiguous"
                )
            PlaywrightArtiscanSession._notify(
                config,
                "scanning",
                "Распознаём артефакты: ждём завершение потока.",
                0,
            )
            deadline = monotonic() + config.timeout_ms / 1000
            trigger = ""
            while monotonic() < deadline:
                probe = page.evaluate(
                    SCAN_STATE_PROBE,
                    {
                        "stallTimeoutMs": config.stall_timeout_ms,
                        "nearEndIdleMs": config.near_end_idle_ms,
                    },
                )
                event = probe.get("event") if isinstance(probe, dict) else None
                progress = probe.get("progress") if isinstance(probe, dict) else None
                normalized_progress = (
                    float(progress) if isinstance(progress, (int, float)) else None
                )
                if normalized_progress is not None:
                    percent = round(normalized_progress * 100)
                    progress_message = (
                        "Artiscan обрабатывает финальный кадр: "
                        f"{percent}%. Ждём завершения OCR."
                        if normalized_progress >= 0.985
                        else f"Artiscan распознаёт видео: {percent}%."
                    )
                    PlaywrightArtiscanSession._notify(
                        config,
                        "scanning",
                        progress_message,
                        normalized_progress,
                    )
                if event in {"black_tail", "near_end_idle", "artiscan_completed"}:
                    trigger = str(event)
                    break
                if event == "ambiguous_stop":
                    raise ArtiscanBrowserError(
                        "Artiscan Stop Scan action is unavailable or ambiguous"
                    )
                if event == "stalled":
                    raise ArtiscanBrowserError(
                        "Artiscan не показывает прогресс "
                        f"{config.stall_timeout_ms / 1000:g} секунд; скан остановлен"
                    )
                if event not in {"running", "waiting"}:
                    raise ArtiscanBrowserError(
                        "Artiscan scan-state probe returned an unknown state"
                    )
                page.wait_for_timeout(250)
            if not trigger:
                raise ArtiscanBrowserError(
                    "Artiscan не завершил распознавание за "
                    f"{config.timeout_ms / 60_000:g} минут"
                )

            stop_control: str | None = None
            if trigger != "artiscan_completed":
                stop_reason = (
                    "Прогресс устойчиво держится у конца видео. Нажимаем Stop Scan."
                    if trigger == "near_end_idle"
                    else "Чёрный хвост найден. Нажимаем Stop Scan."
                )
                PlaywrightArtiscanSession._notify(
                    config,
                    "stopping",
                    stop_reason,
                    1,
                )
                correction_dialog = open_dialogs.filter(
                    has_text="Artifact Correction"
                )
                correction_count = correction_dialog.count()
                if correction_count > 1:
                    raise ArtiscanBrowserError(
                        "Artiscan has multiple open Artifact Correction dialogs"
                    )
                if correction_count == 1:
                    stop_dialog = correction_dialog
                    stop_control = "artifact_correction"
                else:
                    stop_dialog = running_dialog
                    stop_control = "running_scan"
                stop_button = stop_dialog.get_by_role(
                    "button", name="Stop Scan", exact=True
                )
                if stop_button.count() != 1:
                    raise ArtiscanBrowserError(
                        "Artiscan active dialog has no unique Stop Scan action"
                    )
                stop_button.wait_for(state="visible", timeout=30_000)
                if not stop_button.is_enabled():
                    raise ArtiscanBrowserError(
                        "Artiscan Stop Scan action is disabled"
                    )
                stop_button.click()
                running_dialog.wait_for(state="hidden", timeout=120_000)
            PlaywrightArtiscanSession._wait_for_export_ready(page, timeout)
        except timeout as exc:
            raise ArtiscanBrowserError(
                "Artiscan не открыл экспорт после безопасной автоматической остановки"
            ) from exc
        return ScanStopOutcome(trigger=str(trigger), control=stop_control)

    @staticmethod
    def _wait_for_export_ready(page: Any, timeout: type) -> None:
        try:
            page.wait_for_function(
                r"""() => {
                  const match = document.body.innerText.match(
                    /You have ([1-9][0-9]*) artifact\(s\) catalogued\./
                  );
                  const buttons = [...document.querySelectorAll('button')]
                    .filter(item => item.textContent.trim() === 'View Artifacts');
                  return match && buttons.length === 1 && !buttons[0].disabled;
                }""",
                timeout=60_000,
            )
        except timeout as exc:
            raise ArtiscanBrowserError(
                "Artiscan завершил скан, но не открыл каталог для экспорта"
            ) from exc

    @staticmethod
    def _download_good(
        page: Any, config: ArtiscanBrowserConfig, timeout: type
    ) -> dict[str, Any]:
        try:
            view_button = page.get_by_role(
                "button", name="View Artifacts", exact=True
            )
            if view_button.count() != 1 or not view_button.is_enabled():
                raise ArtiscanBrowserError(
                    "Artiscan View Artifacts action is unavailable or ambiguous"
                )
            view_button.click()
            artifacts_dialog = page.locator('dialog[open]').filter(
                has_text="Artifacts"
            )
            artifacts_dialog.wait_for(state="visible", timeout=60_000)
            if artifacts_dialog.count() != 1:
                raise ArtiscanBrowserError(
                    "Artiscan artifacts dialog is unavailable or ambiguous"
                )
            download_button = artifacts_dialog.get_by_role(
                "button", name="Download JSON", exact=True
            )
            download_button.wait_for(state="visible", timeout=60_000)
            if download_button.count() != 1 or not download_button.is_enabled():
                raise ArtiscanBrowserError(
                    "Artiscan Download JSON action is unavailable or ambiguous"
                )
            with page.expect_download(timeout=60_000) as download_info:
                download_button.click()
            download = download_info.value
            with TemporaryDirectory(prefix="grindless-good-") as directory:
                target = Path(directory) / "artifacts.json"
                download.save_as(str(target))
                payload = json.loads(target.read_text(encoding="utf-8"))
        except (timeout, json.JSONDecodeError, OSError) as exc:
            raise ArtiscanBrowserError(
                "Artiscan did not produce a readable GOOD JSON download"
            ) from exc
        if not isinstance(payload, dict):
            raise ArtiscanBrowserError("Artiscan GOOD export root must be an object")
        return payload
