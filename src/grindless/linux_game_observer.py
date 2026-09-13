from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Callable, Sequence

from .linux_game_adapter import EXPECTED_HEIGHT, EXPECTED_WIDTH, LinuxGameControlError


REFERENCE_SCHEMA_VERSION = 1
DEFAULT_REFERENCE_DIRECTORY = Path.home() / ".grindless" / "game-state-references"
DEFAULT_SHADOW_RUN_DIRECTORY = Path.home() / ".grindless" / "game-shadow-runs"
MIN_STATE_CONFIDENCE = 0.95
MIN_STATE_MARGIN = 0.02
DEFAULT_SHADOW_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_TRANSITIONS = 12


class GameScreenState(StrEnum):
    OVERWORLD_READY = "overworld_ready"
    MAP_OPEN = "map_open"
    DOMAIN_ENTRANCE = "domain_entrance"
    PARTY_SETUP = "party_setup"
    COMBAT = "combat"
    REWARD_PROMPT = "reward_prompt"
    REWARD_SCREEN = "reward_screen"
    UNKNOWN = "unknown"


RECORDABLE_STATES = tuple(
    state for state in GameScreenState if state is not GameScreenState.UNKNOWN
)


class ShadowRunOutcome(StrEnum):
    REWARD_OBSERVED = "reward_observed"
    SAFE_STOP = "safe_stop"
    TIME_LIMIT = "time_limit"
    TRANSITION_LIMIT = "transition_limit"


@dataclass(frozen=True)
class ScreenReference:
    reference_id: str
    state: GameScreenState
    filename: str
    captured_at: str
    sha256: str
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


@dataclass(frozen=True)
class StateCandidate:
    state: GameScreenState
    confidence: float
    reference_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "confidence": self.confidence,
            "reference_id": self.reference_id,
        }


@dataclass(frozen=True)
class ScreenStateObservation:
    state: GameScreenState
    confidence: float
    screenshot_sha256: str
    matched_reference_id: str | None
    runner_up_state: GameScreenState | None
    runner_up_confidence: float | None
    reason: str
    candidates: tuple[StateCandidate, ...]

    @property
    def confirmed(self) -> bool:
        return self.state is not GameScreenState.UNKNOWN

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "confidence": self.confidence,
            "screenshot_sha256": self.screenshot_sha256,
            "matched_reference_id": self.matched_reference_id,
            "runner_up_state": (
                self.runner_up_state.value if self.runner_up_state else None
            ),
            "runner_up_confidence": self.runner_up_confidence,
            "reason": self.reason,
            "confirmed": self.confirmed,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True)
class ShadowTraceEvent:
    sequence: int
    elapsed_seconds: float
    state: GameScreenState
    confidence: float
    screenshot_sha256: str
    matched_reference_id: str | None
    transition_from: GameScreenState | None
    reason: str

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["transition_from"] = (
            self.transition_from.value if self.transition_from else None
        )
        return payload


@dataclass(frozen=True)
class ShadowRunResult:
    outcome: ShadowRunOutcome
    reason: str
    transitions: int
    duration_seconds: float
    trace: tuple[ShadowTraceEvent, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "transitions": self.transitions,
            "duration_seconds": self.duration_seconds,
            "input_authority": "none",
            "trace": [event.as_dict() for event in self.trace],
        }


def _load_image_module():
    try:
        from PIL import Image
    except ImportError as exc:
        raise LinuxGameControlError(
            "Screen-state observation needs Pillow; install GrindLess with the game extra"
        ) from exc
    return Image


def _validate_png(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise LinuxGameControlError("Game-state evidence is not a PNG image")
    Image = _load_image_module()
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            size = image.size
    except Exception as exc:
        raise LinuxGameControlError("Game-state evidence is an unreadable PNG") from exc
    if size != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        raise LinuxGameControlError(
            f"Expected a {EXPECTED_WIDTH}x{EXPECTED_HEIGHT} game capture, observed {size[0]}x{size[1]}"
        )
    return size


def _descriptor(payload: bytes) -> tuple[int, ...]:
    _validate_png(payload)
    Image = _load_image_module()
    with Image.open(io.BytesIO(payload)) as image:
        grayscale = image.convert("L").resize((64, 36), Image.Resampling.BILINEAR)
        flattened = getattr(grayscale, "get_flattened_data", None)
        return tuple(flattened() if flattened else grayscale.getdata())


def _similarity(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("screen descriptors must have the same non-zero length")
    distance = sum(abs(a - b) for a, b in zip(left, right, strict=True))
    return max(0.0, 1.0 - distance / (255.0 * len(left)))


class ScreenReferenceStore:
    """Versioned local evidence captured from the operator's exact game setup."""

    def __init__(self, directory: Path = DEFAULT_REFERENCE_DIRECTORY) -> None:
        self.directory = directory
        self.manifest_path = directory / "manifest.json"

    def _manifest(self) -> dict[str, object]:
        if not self.manifest_path.exists():
            return {
                "schema_version": REFERENCE_SCHEMA_VERSION,
                "capture_size": [EXPECTED_WIDTH, EXPECTED_HEIGHT],
                "references": [],
            }
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LinuxGameControlError(
                f"Could not read game-state manifest: {self.manifest_path}"
            ) from exc
        if payload.get("schema_version") != REFERENCE_SCHEMA_VERSION:
            raise LinuxGameControlError("Unsupported game-state reference schema")
        if payload.get("capture_size") != [EXPECTED_WIDTH, EXPECTED_HEIGHT]:
            raise LinuxGameControlError("Game-state references use another capture size")
        if not isinstance(payload.get("references"), list):
            raise LinuxGameControlError("Game-state manifest has no reference list")
        return payload

    def references(self) -> tuple[ScreenReference, ...]:
        items: list[ScreenReference] = []
        for raw in self._manifest()["references"]:
            try:
                item = ScreenReference(
                    reference_id=str(raw["reference_id"]),
                    state=GameScreenState(str(raw["state"])),
                    filename=str(raw["filename"]),
                    captured_at=str(raw["captured_at"]),
                    sha256=str(raw["sha256"]),
                    note=str(raw.get("note", "")),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise LinuxGameControlError(
                    "Game-state manifest contains an invalid reference"
                ) from exc
            if item.state is GameScreenState.UNKNOWN:
                raise LinuxGameControlError("Unknown cannot be stored as a reference state")
            items.append(item)
        return tuple(items)

    def record(
        self,
        state: GameScreenState,
        payload: bytes,
        *,
        note: str = "",
        captured_at: datetime | None = None,
    ) -> ScreenReference:
        if state is GameScreenState.UNKNOWN:
            raise ValueError("unknown cannot be recorded as a trusted reference")
        _validate_png(payload)
        digest = hashlib.sha256(payload).hexdigest()
        timestamp = (captured_at or datetime.now(UTC)).astimezone(UTC)
        reference_id = f"{state.value}-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{digest[:12]}"
        filename = f"{reference_id}.png"
        reference = ScreenReference(
            reference_id=reference_id,
            state=state,
            filename=filename,
            captured_at=timestamp.isoformat(),
            sha256=digest,
            note=note.strip(),
        )
        manifest = self._manifest()
        existing = [
            item
            for item in manifest["references"]
            if item.get("reference_id") != reference.reference_id
        ]
        existing.append(reference.as_dict())
        manifest["references"] = existing
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / filename).write_bytes(payload)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)
        return reference

    def reference_payload(self, reference: ScreenReference) -> bytes:
        path = self.directory / reference.filename
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise LinuxGameControlError(f"Missing game-state reference: {path}") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if digest != reference.sha256:
            raise LinuxGameControlError(
                f"Game-state reference checksum changed: {reference.reference_id}"
            )
        return payload


class CalibratedScreenClassifier:
    """Strict nearest-reference classifier; ambiguity is an unknown state."""

    def __init__(
        self,
        store: ScreenReferenceStore,
        *,
        minimum_confidence: float = MIN_STATE_CONFIDENCE,
        minimum_margin: float = MIN_STATE_MARGIN,
    ) -> None:
        if not 0.0 < minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be in (0, 1]")
        if not 0.0 <= minimum_margin <= 1.0:
            raise ValueError("minimum_margin must be in [0, 1]")
        self.store = store
        self.minimum_confidence = minimum_confidence
        self.minimum_margin = minimum_margin
        self._references = tuple(
            (reference, _descriptor(store.reference_payload(reference)))
            for reference in store.references()
        )

    def classify(self, payload: bytes) -> ScreenStateObservation:
        observed_digest = hashlib.sha256(payload).hexdigest()
        observed = _descriptor(payload)
        if not self._references:
            return ScreenStateObservation(
                state=GameScreenState.UNKNOWN,
                confidence=0.0,
                screenshot_sha256=observed_digest,
                matched_reference_id=None,
                runner_up_state=None,
                runner_up_confidence=None,
                reason="no_calibrated_references",
                candidates=(),
            )

        best_by_state: dict[GameScreenState, StateCandidate] = {}
        for reference, reference_descriptor in self._references:
            score = _similarity(observed, reference_descriptor)
            candidate = StateCandidate(reference.state, score, reference.reference_id)
            previous = best_by_state.get(reference.state)
            if previous is None or candidate.confidence > previous.confidence:
                best_by_state[reference.state] = candidate
        candidates = tuple(
            sorted(best_by_state.values(), key=lambda item: item.confidence, reverse=True)
        )
        best = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        margin = best.confidence - (runner_up.confidence if runner_up else 0.0)
        if best.confidence < self.minimum_confidence:
            state = GameScreenState.UNKNOWN
            reason = "confidence_below_threshold"
        elif runner_up is not None and margin < self.minimum_margin:
            state = GameScreenState.UNKNOWN
            reason = "ambiguous_state"
        else:
            state = best.state
            reason = "calibrated_reference_match"
        return ScreenStateObservation(
            state=state,
            confidence=best.confidence,
            screenshot_sha256=observed_digest,
            matched_reference_id=best.reference_id,
            runner_up_state=runner_up.state if runner_up else None,
            runner_up_confidence=runner_up.confidence if runner_up else None,
            reason=reason,
            candidates=candidates,
        )


ALLOWED_SHADOW_TRANSITIONS: dict[GameScreenState, frozenset[GameScreenState]] = {
    GameScreenState.OVERWORLD_READY: frozenset(
        {GameScreenState.MAP_OPEN, GameScreenState.DOMAIN_ENTRANCE}
    ),
    GameScreenState.MAP_OPEN: frozenset(
        {GameScreenState.OVERWORLD_READY, GameScreenState.DOMAIN_ENTRANCE}
    ),
    GameScreenState.DOMAIN_ENTRANCE: frozenset(
        {GameScreenState.PARTY_SETUP, GameScreenState.OVERWORLD_READY}
    ),
    GameScreenState.PARTY_SETUP: frozenset(
        {GameScreenState.COMBAT, GameScreenState.DOMAIN_ENTRANCE}
    ),
    GameScreenState.COMBAT: frozenset(
        {GameScreenState.REWARD_PROMPT, GameScreenState.OVERWORLD_READY}
    ),
    GameScreenState.REWARD_PROMPT: frozenset(
        {GameScreenState.REWARD_SCREEN, GameScreenState.COMBAT}
    ),
    GameScreenState.REWARD_SCREEN: frozenset(
        {
            GameScreenState.DOMAIN_ENTRANCE,
            GameScreenState.PARTY_SETUP,
            GameScreenState.OVERWORLD_READY,
        }
    ),
}


class ShadowGameObserver:
    """Observe a route and prove state transitions without issuing any input."""

    def __init__(
        self,
        capture: Callable[[], bytes],
        classifier: CalibratedScreenClassifier,
        *,
        stop_requested: Callable[[], bool] | None = None,
        evidence_sink: (
            Callable[[int, bytes, ScreenStateObservation], None] | None
        ) = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.capture = capture
        self.classifier = classifier
        self.stop_requested = stop_requested or (lambda: False)
        self.evidence_sink = evidence_sink
        self.clock = clock
        self.sleep = sleep

    def run(
        self,
        *,
        interval_seconds: float = 1.0,
        timeout_seconds: float = DEFAULT_SHADOW_TIMEOUT_SECONDS,
        max_transitions: int = DEFAULT_MAX_TRANSITIONS,
    ) -> ShadowRunResult:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_transitions <= 0:
            raise ValueError("max_transitions must be positive")

        started = self.clock()
        previous: GameScreenState | None = None
        transitions = 0
        trace: list[ShadowTraceEvent] = []
        while True:
            elapsed = self.clock() - started
            if self.stop_requested():
                return self._result(
                    ShadowRunOutcome.SAFE_STOP,
                    "operator_stop_requested",
                    transitions,
                    elapsed,
                    trace,
                )
            if elapsed >= timeout_seconds:
                return self._result(
                    ShadowRunOutcome.TIME_LIMIT,
                    "shadow_time_limit_reached",
                    transitions,
                    elapsed,
                    trace,
                )

            frame = self.capture()
            observation = self.classifier.classify(frame)
            if self.evidence_sink is not None:
                self.evidence_sink(len(trace) + 1, frame, observation)
            changed = previous is not None and observation.state is not previous
            event_reason = observation.reason
            if observation.state is GameScreenState.UNKNOWN:
                event_reason = f"safe_stop:{observation.reason}"
            elif changed and observation.state not in ALLOWED_SHADOW_TRANSITIONS.get(
                previous, frozenset()
            ):
                event_reason = "safe_stop:illegal_state_transition"
            trace.append(
                ShadowTraceEvent(
                    sequence=len(trace) + 1,
                    elapsed_seconds=elapsed,
                    state=observation.state,
                    confidence=observation.confidence,
                    screenshot_sha256=observation.screenshot_sha256,
                    matched_reference_id=observation.matched_reference_id,
                    transition_from=previous if changed else None,
                    reason=event_reason,
                )
            )
            if observation.state is GameScreenState.UNKNOWN:
                return self._result(
                    ShadowRunOutcome.SAFE_STOP,
                    observation.reason,
                    transitions,
                    elapsed,
                    trace,
                )
            if changed:
                if observation.state not in ALLOWED_SHADOW_TRANSITIONS.get(
                    previous, frozenset()
                ):
                    return self._result(
                        ShadowRunOutcome.SAFE_STOP,
                        "illegal_state_transition",
                        transitions,
                        elapsed,
                        trace,
                    )
                transitions += 1
                if transitions > max_transitions:
                    return self._result(
                        ShadowRunOutcome.TRANSITION_LIMIT,
                        "shadow_transition_limit_reached",
                        transitions,
                        elapsed,
                        trace,
                    )
            previous = observation.state
            if observation.state is GameScreenState.REWARD_SCREEN:
                return self._result(
                    ShadowRunOutcome.REWARD_OBSERVED,
                    "reward_screen_confirmed",
                    transitions,
                    elapsed,
                    trace,
                )
            self.sleep(interval_seconds)

    @staticmethod
    def _result(
        outcome: ShadowRunOutcome,
        reason: str,
        transitions: int,
        duration_seconds: float,
        trace: Sequence[ShadowTraceEvent],
    ) -> ShadowRunResult:
        return ShadowRunResult(
            outcome=outcome,
            reason=reason,
            transitions=transitions,
            duration_seconds=duration_seconds,
            trace=tuple(trace),
        )


class ShadowEvidenceWriter:
    """Persist the exact local frames behind a shadow result for later triage."""

    def __init__(
        self,
        root: Path = DEFAULT_SHADOW_RUN_DIRECTORY,
        *,
        started_at: datetime | None = None,
    ) -> None:
        timestamp = (started_at or datetime.now(UTC)).astimezone(UTC)
        self.run_id = timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
        self.directory = root / self.run_id

    def record(
        self,
        sequence: int,
        payload: bytes,
        observation: ScreenStateObservation,
    ) -> None:
        _validate_png(payload)
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{sequence:04d}-{observation.state.value}-"
            f"{observation.screenshot_sha256[:12]}.png"
        )
        (self.directory / filename).write_bytes(payload)

    def finish(self, result: ShadowRunResult) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "evidence_directory": str(self.directory),
            **result.as_dict(),
        }
        target = self.directory / "result.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
        return target
