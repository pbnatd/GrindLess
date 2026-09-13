from __future__ import annotations

import io
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from grindless.linux_game_observer import (
    CalibratedScreenClassifier,
    GameScreenState,
    ScreenReferenceStore,
    ShadowEvidenceWriter,
    ShadowGameObserver,
    ShadowRunOutcome,
)


def png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1920, 1080), color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class SequenceCapture:
    def __init__(self, frames: list[bytes]) -> None:
        self.frames = frames
        self.index = 0

    def __call__(self) -> bytes:
        frame = self.frames[min(self.index, len(self.frames) - 1)]
        self.index += 1
        return frame


class ScreenReferenceStoreTests(unittest.TestCase):
    def test_record_preserves_versioned_evidence_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenReferenceStore(Path(directory))
            reference = store.record(
                GameScreenState.MAP_OPEN,
                png((10, 20, 30)),
                note="map opened manually",
                captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            )

            loaded = store.references()

            self.assertEqual(loaded, (reference,))
            self.assertEqual(reference.state, GameScreenState.MAP_OPEN)
            self.assertEqual(reference.note, "map opened manually")
            self.assertEqual(store.reference_payload(reference), png((10, 20, 30)))
            self.assertTrue((Path(directory) / "manifest.json").exists())

    def test_record_rejects_wrong_capture_size(self) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (1280, 720), (0, 0, 0)).save(buffer, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenReferenceStore(Path(directory))

            with self.assertRaisesRegex(Exception, "1920x1080"):
                store.record(GameScreenState.COMBAT, buffer.getvalue())


class CalibratedScreenClassifierTests(unittest.TestCase):
    def test_identical_capture_is_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenReferenceStore(Path(directory))
            store.record(GameScreenState.OVERWORLD_READY, png((20, 40, 60)))
            store.record(GameScreenState.MAP_OPEN, png((220, 220, 220)))

            result = CalibratedScreenClassifier(store).classify(png((20, 40, 60)))

            self.assertTrue(result.confirmed)
            self.assertEqual(result.state, GameScreenState.OVERWORLD_READY)
            self.assertEqual(result.confidence, 1.0)

    def test_unknown_capture_fails_closed_below_confidence_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenReferenceStore(Path(directory))
            store.record(GameScreenState.OVERWORLD_READY, png((0, 0, 0)))

            result = CalibratedScreenClassifier(store).classify(png((255, 255, 255)))

            self.assertFalse(result.confirmed)
            self.assertEqual(result.state, GameScreenState.UNKNOWN)
            self.assertEqual(result.reason, "confidence_below_threshold")

    def test_equal_matches_for_different_states_are_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ScreenReferenceStore(Path(directory))
            same = png((80, 100, 120))
            store.record(GameScreenState.COMBAT, same)
            store.record(GameScreenState.REWARD_PROMPT, same)

            result = CalibratedScreenClassifier(store).classify(same)

            self.assertFalse(result.confirmed)
            self.assertEqual(result.reason, "ambiguous_state")


class ShadowGameObserverTests(unittest.TestCase):
    def calibrated(self, directory: Path) -> tuple[CalibratedScreenClassifier, dict[GameScreenState, bytes]]:
        colors = {
            GameScreenState.OVERWORLD_READY: (10, 10, 10),
            GameScreenState.MAP_OPEN: (45, 45, 45),
            GameScreenState.DOMAIN_ENTRANCE: (80, 80, 80),
            GameScreenState.PARTY_SETUP: (115, 115, 115),
            GameScreenState.COMBAT: (150, 150, 150),
            GameScreenState.REWARD_PROMPT: (190, 190, 190),
            GameScreenState.REWARD_SCREEN: (230, 230, 230),
        }
        frames = {state: png(color) for state, color in colors.items()}
        store = ScreenReferenceStore(directory)
        for state, frame in frames.items():
            store.record(state, frame)
        return CalibratedScreenClassifier(store), frames

    def test_legal_shadow_route_reaches_reward_without_input_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, frames = self.calibrated(Path(directory))
            route = [
                frames[GameScreenState.OVERWORLD_READY],
                frames[GameScreenState.MAP_OPEN],
                frames[GameScreenState.DOMAIN_ENTRANCE],
                frames[GameScreenState.PARTY_SETUP],
                frames[GameScreenState.COMBAT],
                frames[GameScreenState.REWARD_PROMPT],
                frames[GameScreenState.REWARD_SCREEN],
            ]
            clock = FakeClock()
            result = ShadowGameObserver(
                SequenceCapture(route),
                classifier,
                clock=clock,
                sleep=clock.sleep,
            ).run(interval_seconds=0.5)

            self.assertEqual(result.outcome, ShadowRunOutcome.REWARD_OBSERVED)
            self.assertEqual(result.transitions, 6)
            self.assertEqual(result.reason, "reward_screen_confirmed")
            self.assertEqual(result.as_dict()["input_authority"], "none")

    def test_unknown_state_stops_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, _ = self.calibrated(Path(directory))
            clock = FakeClock()
            result = ShadowGameObserver(
                SequenceCapture([png((132, 132, 132))]),
                classifier,
                clock=clock,
                sleep=clock.sleep,
            ).run()

            self.assertEqual(result.outcome, ShadowRunOutcome.SAFE_STOP)
            self.assertEqual(result.reason, "confidence_below_threshold")
            self.assertEqual(len(result.trace), 1)

    def test_illegal_transition_stops_and_records_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, frames = self.calibrated(Path(directory))
            clock = FakeClock()
            result = ShadowGameObserver(
                SequenceCapture(
                    [
                        frames[GameScreenState.OVERWORLD_READY],
                        frames[GameScreenState.REWARD_SCREEN],
                    ]
                ),
                classifier,
                clock=clock,
                sleep=clock.sleep,
            ).run()

            self.assertEqual(result.outcome, ShadowRunOutcome.SAFE_STOP)
            self.assertEqual(result.reason, "illegal_state_transition")
            self.assertEqual(result.trace[-1].transition_from, GameScreenState.OVERWORLD_READY)

    def test_operator_stop_prevents_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, frames = self.calibrated(Path(directory))
            capture = SequenceCapture([frames[GameScreenState.OVERWORLD_READY]])
            result = ShadowGameObserver(
                capture,
                classifier,
                stop_requested=lambda: True,
            ).run()

            self.assertEqual(result.outcome, ShadowRunOutcome.SAFE_STOP)
            self.assertEqual(result.reason, "operator_stop_requested")
            self.assertEqual(capture.index, 0)

    def test_time_limit_stops_a_static_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, frames = self.calibrated(Path(directory))
            clock = FakeClock()
            result = ShadowGameObserver(
                SequenceCapture([frames[GameScreenState.OVERWORLD_READY]]),
                classifier,
                clock=clock,
                sleep=clock.sleep,
            ).run(interval_seconds=1.0, timeout_seconds=2.0)

            self.assertEqual(result.outcome, ShadowRunOutcome.TIME_LIMIT)
            self.assertEqual(result.reason, "shadow_time_limit_reached")
            self.assertEqual(len(result.trace), 2)

    def test_transition_limit_stops_before_route_can_continue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            classifier, frames = self.calibrated(Path(directory))
            clock = FakeClock()
            result = ShadowGameObserver(
                SequenceCapture(
                    [
                        frames[GameScreenState.OVERWORLD_READY],
                        frames[GameScreenState.MAP_OPEN],
                        frames[GameScreenState.OVERWORLD_READY],
                    ]
                ),
                classifier,
                clock=clock,
                sleep=clock.sleep,
            ).run(max_transitions=1)

            self.assertEqual(result.outcome, ShadowRunOutcome.TRANSITION_LIMIT)
            self.assertEqual(result.reason, "shadow_transition_limit_reached")
            self.assertEqual(result.transitions, 2)

    def test_shadow_evidence_keeps_frames_and_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            classifier, frames = self.calibrated(root / "references")
            evidence = ShadowEvidenceWriter(
                root / "runs",
                started_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            )
            result = ShadowGameObserver(
                SequenceCapture([frames[GameScreenState.REWARD_SCREEN]]),
                classifier,
                evidence_sink=evidence.record,
            ).run()

            result_path = evidence.finish(result)

            self.assertTrue(result_path.exists())
            self.assertEqual(len(tuple(evidence.directory.glob("*.png"))), 1)
            self.assertIn('"input_authority": "none"', result_path.read_text())
            self.assertIn('"reward_observed"', result_path.read_text())


if __name__ == "__main__":
    unittest.main()
