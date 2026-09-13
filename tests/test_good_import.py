from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from grindless.artiscan_browser import (
    ARTISCAN_ORIGIN,
    SCAN_STATE_PROBE,
    ArtiscanBrowserConfig,
    ArtiscanBrowserError,
    ArtiscanExtractionAudit,
    ArtiscanNetworkPolicy,
    BrowserArtiscanExtractor,
    PlaywrightArtiscanSession,
)
from grindless.good_import import import_good, load_good
from grindless.inventory_input import load_inventory_input
from grindless.models import Slot, Stat
from grindless.resource_monitor import ResourceMeasurement

EXAMPLE = Path(__file__).parents[1] / "examples" / "xiangling.good.json"
MAVUIKA_V3 = Path(__file__).parents[1] / "examples" / "mavuika.good-v3.json"


class FakeArtiscanRunner:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.received_path: Path | None = None

    def run(
        self, video_path: Path, config: ArtiscanBrowserConfig
    ) -> tuple[dict[str, object], ArtiscanExtractionAudit]:
        self.received_path = video_path
        return self.payload, ArtiscanExtractionAudit(
            site_build=config.expected_build,
            browser_was_offline_before_video=True,
        )


class FakeProfiler:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> ResourceMeasurement:
        self.stopped = True
        return ResourceMeasurement(
            wall_time_seconds=12.3456,
            peak_python_rss_bytes=10_000_000,
            peak_process_tree_rss_bytes=250_000_000,
            sampling_interval_ms=100,
            samples=124,
            complete=True,
        )


class GoodImportTests(unittest.TestCase):
    def test_imports_good_v3_character_weapon_and_inactive_substat(self) -> None:
        inventory = load_good(MAVUIKA_V3)
        character = inventory.character("Mavuika")
        weapon = inventory.equipped_weapon("Mavuika")

        self.assertIsNotNone(character)
        self.assertEqual(character.level, 90)
        self.assertEqual(character.constellation, 2)
        self.assertEqual(character.talents.skill, 10)
        self.assertIsNotNone(weapon)
        self.assertEqual(weapon.key, "WolfsGravestone")
        self.assertEqual(weapon.refinement, 1)
        self.assertEqual(inventory.report.inactive_substats_imported, 1)
        sands = inventory.artifacts[2]
        self.assertEqual(len(sands.substats), 3)
        self.assertEqual(len(sands.known_substats), 4)
        self.assertEqual(sands.unactivated_substats[0].stat, Stat.ENERGY_RECHARGE)

    def test_imports_inventory_and_complete_equipped_build(self) -> None:
        inventory = load_good(EXAMPLE)
        state = inventory.to_account_state("Xiangling")

        self.assertEqual(inventory.report.artifacts_imported, 6)
        self.assertEqual(len(state.character.equipped_artifact_ids), 5)
        self.assertEqual(
            state.equipped_build().artifacts[Slot.GOBLET].main_stat, Stat.PYRO_DMG
        )
        self.assertTrue(all(item.main_value is None for item in inventory.artifacts))

    def test_ids_are_stable_for_the_same_export(self) -> None:
        first = load_good(EXAMPLE)
        second = load_good(EXAMPLE)
        self.assertEqual(
            [item.id for item in first.artifacts],
            [item.id for item in second.artifacts],
        )
        self.assertEqual(
            [item.source_index for item in first.artifacts],
            list(range(1, len(first.artifacts) + 1)),
        )

    def test_unknown_stat_key_fails_loudly(self) -> None:
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        broken = copy.deepcopy(payload)
        broken["artifacts"][0]["substats"][0]["key"] = "futureMysteryStat_"

        with self.assertRaisesRegex(ValueError, "unknown GOOD substats"):
            import_good(broken)

    def test_unknown_good_version_is_rejected(self) -> None:
        payload = json.loads(MAVUIKA_V3.read_text(encoding="utf-8"))
        payload["version"] = 4

        with self.assertRaisesRegex(ValueError, "version"):
            import_good(payload)

    def test_duplicate_equipped_weapon_is_rejected(self) -> None:
        payload = json.loads(MAVUIKA_V3.read_text(encoding="utf-8"))
        payload["weapons"].append(
            {
                "key": "WolfsGravestone",
                "level": 90,
                "ascension": 6,
                "refinement": 1,
                "location": "Mavuika",
                "lock": False,
            }
        )

        with self.assertRaisesRegex(ValueError, "more than one weapon"):
            import_good(payload)

    def test_duplicate_equipped_slot_is_rejected(self) -> None:
        payload = json.loads(MAVUIKA_V3.read_text(encoding="utf-8"))
        payload["artifacts"][0]["location"] = "Mavuika"
        duplicate = copy.deepcopy(payload["artifacts"][0])
        duplicate["lock"] = False
        payload["artifacts"].append(duplicate)

        with self.assertRaisesRegex(ValueError, "more than one flower"):
            import_good(payload)

    def test_incomplete_equipped_build_is_rejected_only_when_selected(self) -> None:
        inventory = load_good(EXAMPLE)

        with self.assertRaisesRegex(ValueError, "missing"):
            inventory.to_account_state("NotEquipped")

    def test_json_extension_can_contain_good_schema(self) -> None:
        inventory = load_inventory_input(EXAMPLE)

        self.assertEqual(inventory.report.source, "GrindLessExample")
        self.assertEqual(inventory.report.artifacts_imported, 6)

    def test_video_without_extractor_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "Artiscan-compatible extractor"):
            load_inventory_input("inventory.mp4")

    def test_browser_extractor_normalizes_video_to_good(self) -> None:
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        runner = FakeArtiscanRunner(payload)
        profiler = FakeProfiler()
        extractor = BrowserArtiscanExtractor(
            runner=runner, profiler_factory=lambda: profiler
        )
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "inventory.mp4"
            video.write_bytes(b"test video boundary")

            inventory = load_inventory_input(video, video_extractor=extractor)

        self.assertEqual(inventory.report.artifacts_imported, 6)
        self.assertEqual(runner.received_path, video.resolve())
        self.assertTrue(extractor.last_audit.browser_was_offline_before_video)
        self.assertEqual(extractor.last_audit.artifacts_exported, 6)
        self.assertTrue(profiler.started)
        self.assertTrue(profiler.stopped)
        self.assertEqual(
            extractor.last_audit.as_dict()["performance"],
            {
                "wall_time_seconds": 12.346,
                "peak_python_rss_bytes": 10_000_000,
                "peak_process_tree_rss_bytes": 250_000_000,
                "sampling_interval_ms": 100,
                "samples": 124,
                "complete": True,
                "warnings": [],
                "memory_metric": (
                    "sampled sum of RSS for Python and descendant processes"
                ),
            },
        )
        self.assertEqual(extractor.last_good, payload)

    def test_automated_actions_are_exposed_in_audit(self) -> None:
        audit = ArtiscanExtractionAudit(
            interaction_mode="fully_automated",
            automated_actions=[
                "decline_video_transcoding",
                "stop_scan_at_black_tail",
            ],
            scan_stop_trigger="black_tail",
            scan_stop_control="running_scan",
        ).as_dict()

        self.assertEqual(audit["interaction_mode"], "fully_automated")
        self.assertEqual(audit["manual_checkpoints"], [])
        self.assertEqual(
            audit["automated_actions"],
            ["decline_video_transcoding", "stop_scan_at_black_tail"],
        )
        self.assertEqual(audit["scan_stop_trigger"], "black_tail")
        self.assertEqual(audit["scan_stop_control"], "running_scan")

    def test_transcoding_is_declined_with_an_exact_no_action(self) -> None:
        page = MagicMock()
        prompt = MagicMock()
        no_button = MagicMock()
        prompt.count.return_value = 1
        no_button.count.return_value = 1
        page.get_by_text.return_value = prompt
        page.get_by_role.return_value = no_button

        outcome = PlaywrightArtiscanSession._decline_transcoding(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome, "declined")
        page.get_by_text.assert_called_once_with(
            "Would you like to transcode the video?", exact=True
        )
        page.get_by_role.assert_called_once_with("button", name="No", exact=True)
        no_button.click.assert_called_once_with()
        prompt.wait_for.assert_any_call(state="visible", timeout=30_000)
        prompt.wait_for.assert_any_call(state="hidden", timeout=30_000)

    def test_missing_transcoding_prompt_is_valid_when_configure_is_visible(self) -> None:
        page = MagicMock()
        prompt = MagicMock()
        configure = MagicMock()
        prompt.wait_for.side_effect = TimeoutError("prompt skipped")
        page.get_by_text.return_value = prompt
        page.get_by_role.return_value = configure

        outcome = PlaywrightArtiscanSession._decline_transcoding(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome, "not_present")
        page.get_by_role.assert_called_once_with(
            "button", name="Configure", exact=True
        )
        configure.wait_for.assert_called_once_with(state="visible", timeout=30_000)

    def test_scan_stops_after_detected_black_tail(self) -> None:
        page = MagicMock()
        start_button = MagicMock()
        stop_button = MagicMock()
        open_dialogs = MagicMock()
        running_dialog = MagicMock()
        correction_dialog = MagicMock()
        stop_button.count.return_value = 1
        stop_button.is_enabled.return_value = True
        running_dialog.count.return_value = 1
        running_dialog.get_by_role.return_value = stop_button
        correction_dialog.count.return_value = 0
        open_dialogs.filter.side_effect = [running_dialog, correction_dialog]
        page.get_by_role.return_value = start_button
        page.locator.return_value = open_dialogs
        page.evaluate.side_effect = [
            None,
            {"event": "black_tail", "progress": 0.91},
        ]

        outcome = PlaywrightArtiscanSession._run_scan(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome.trigger, "black_tail")
        self.assertEqual(outcome.control, "running_scan")
        start_button.click.assert_called_once_with(timeout=30_000)
        stop_button.click.assert_called_once_with()
        page.get_by_role.assert_called_once_with(
            "button", name="Start Scan", exact=True
        )
        running_dialog.get_by_role.assert_called_once_with(
            "button", name="Stop Scan", exact=True
        )
        running_dialog.wait_for.assert_called_once_with(
            state="hidden", timeout=120_000
        )

    def test_scan_accepts_artiscan_natural_completion_without_stop_click(self) -> None:
        page = MagicMock()
        start_button = MagicMock()
        open_dialogs = MagicMock()
        running_dialog = MagicMock()
        running_dialog.count.return_value = 1
        open_dialogs.filter.return_value = running_dialog
        page.get_by_role.return_value = start_button
        page.locator.return_value = open_dialogs
        page.evaluate.side_effect = [
            None,
            {"event": "artiscan_completed", "progress": 1},
        ]

        outcome = PlaywrightArtiscanSession._run_scan(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome.trigger, "artiscan_completed")
        self.assertIsNone(outcome.control)
        running_dialog.get_by_role.assert_not_called()
        running_dialog.wait_for.assert_not_called()

    def test_scan_stops_after_stable_near_end_progress(self) -> None:
        page = MagicMock()
        start_button = MagicMock()
        stop_button = MagicMock()
        open_dialogs = MagicMock()
        running_dialog = MagicMock()
        correction_dialog = MagicMock()
        stop_button.count.return_value = 1
        stop_button.is_enabled.return_value = True
        running_dialog.count.return_value = 1
        running_dialog.get_by_role.return_value = stop_button
        correction_dialog.count.return_value = 0
        open_dialogs.filter.side_effect = [running_dialog, correction_dialog]
        page.get_by_role.return_value = start_button
        page.locator.return_value = open_dialogs
        page.evaluate.side_effect = [
            None,
            {
                "event": "near_end_idle",
                "progress": 0.99,
                "cataloguedCount": 108,
                "idleMs": 30_000,
            },
        ]

        outcome = PlaywrightArtiscanSession._run_scan(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome.trigger, "near_end_idle")
        self.assertEqual(outcome.control, "running_scan")
        stop_button.click.assert_called_once_with()
        running_dialog.wait_for.assert_called_once_with(
            state="hidden", timeout=120_000
        )

    def test_scan_stops_through_artifact_correction_when_it_is_open(self) -> None:
        page = MagicMock()
        start_button = MagicMock()
        correction_stop = MagicMock()
        open_dialogs = MagicMock()
        running_dialog = MagicMock()
        correction_dialog = MagicMock()
        running_dialog.count.return_value = 1
        correction_dialog.count.return_value = 1
        correction_stop.count.return_value = 1
        correction_stop.is_enabled.return_value = True
        correction_dialog.get_by_role.return_value = correction_stop
        open_dialogs.filter.side_effect = [running_dialog, correction_dialog]
        page.get_by_role.return_value = start_button
        page.locator.return_value = open_dialogs
        page.evaluate.side_effect = [
            None,
            {
                "event": "near_end_idle",
                "progress": 0.99,
                "cataloguedCount": 108,
                "idleMs": 30_000,
            },
        ]

        outcome = PlaywrightArtiscanSession._run_scan(
            page, ArtiscanBrowserConfig(), TimeoutError
        )

        self.assertEqual(outcome.trigger, "near_end_idle")
        self.assertEqual(outcome.control, "artifact_correction")
        correction_dialog.get_by_role.assert_called_once_with(
            "button", name="Stop Scan", exact=True
        )
        correction_stop.click.assert_called_once_with()
        running_dialog.get_by_role.assert_not_called()
        running_dialog.wait_for.assert_called_once_with(
            state="hidden", timeout=120_000
        )

    def test_scan_probe_targets_artiscan_canvas_not_missing_video_element(self) -> None:
        self.assertIn("dialog.querySelectorAll('canvas')", SCAN_STATE_PROBE)
        self.assertNotIn("querySelectorAll('video')", SCAN_STATE_PROBE)
        self.assertIn("near_end_idle", SCAN_STATE_PROBE)
        self.assertIn("cataloguedCount > 0", SCAN_STATE_PROBE)

    def test_near_end_timeout_must_precede_general_stall_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "shorter than stall timeout"):
            ArtiscanBrowserConfig(
                near_end_idle_ms=90_000,
                stall_timeout_ms=90_000,
            )

    def test_scan_fails_loudly_when_artiscan_stalls(self) -> None:
        page = MagicMock()
        open_dialogs = MagicMock()
        running_dialog = MagicMock()
        running_dialog.count.return_value = 1
        open_dialogs.filter.return_value = running_dialog
        page.locator.return_value = open_dialogs
        page.evaluate.side_effect = [
            None,
            {"event": "stalled", "progress": 0.42},
        ]

        with self.assertRaisesRegex(ArtiscanBrowserError, "90 секунд"):
            PlaywrightArtiscanSession._run_scan(
                page, ArtiscanBrowserConfig(), TimeoutError
            )

    def test_browser_extractor_rejects_empty_good_export(self) -> None:
        payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        runner = FakeArtiscanRunner(payload)
        extractor = BrowserArtiscanExtractor(
            runner=runner, profiler_factory=FakeProfiler
        )
        empty_payload = {
            "format": "GOOD",
            "source": "Artiscan",
            "version": 1,
            "artifacts": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "inventory.mp4"
            video.write_bytes(b"test video boundary")
            extractor.extract_good(video)
            runner.payload = empty_payload
            with self.assertRaisesRegex(ArtiscanBrowserError, "zero artifacts"):
                extractor.extract_good(video)

        self.assertIsNone(extractor.last_good)
        self.assertIsNotNone(extractor.last_audit)

    def test_browser_extractor_rejects_non_good_document(self) -> None:
        extractor = BrowserArtiscanExtractor(
            runner=FakeArtiscanRunner({"format": "UNKNOWN", "artifacts": [{}]}),
            profiler_factory=FakeProfiler,
        )
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "inventory.mp4"
            video.write_bytes(b"test video boundary")
            with self.assertRaisesRegex(ArtiscanBrowserError, "not a GOOD"):
                extractor.extract_good(video)

    def test_artiscan_network_policy_allows_only_same_origin_gets(self) -> None:
        policy = ArtiscanNetworkPolicy()

        allowed = policy.decide("GET", f"{ARTISCAN_ORIGIN}/manifest.json", "fetch")
        foreign = policy.decide("GET", "https://example.com/model.bin", "fetch")
        upload = policy.decide("POST", f"{ARTISCAN_ORIGIN}/upload", "fetch")
        socket = policy.decide("GET", f"{ARTISCAN_ORIGIN}/socket", "websocket")

        self.assertTrue(allowed.allowed)
        self.assertFalse(foreign.allowed)
        self.assertFalse(upload.allowed)
        self.assertFalse(socket.allowed)


if __name__ == "__main__":
    unittest.main()
