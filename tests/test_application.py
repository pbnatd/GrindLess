from __future__ import annotations

import unittest

from grindless.application import (
    MavuikaFarmSimulationRequest,
    analyze_mavuika_inventory,
    describe_mavuika_preset,
    simulate_mavuika_farm,
)
from grindless.models import FarmPolicy, Slot


def good_artifact(
    slot: str,
    main_stat: str,
    substats: list[str],
    set_name: str = "ObsidianCodex",
) -> dict[str, object]:
    return {
        "setKey": set_name,
        "slotKey": slot,
        "level": 0,
        "rarity": 5,
        "mainStatKey": main_stat,
        "location": "",
        "lock": False,
        "substats": [
            {"key": key, "value": index + 1}
            for index, key in enumerate(substats)
        ],
    }


class ApplicationServiceTests(unittest.TestCase):
    def test_preset_projection_keeps_the_atk_em_sands_conflict(self) -> None:
        preset, goals = describe_mavuika_preset(FarmPolicy.ECONOMY)
        sands = next(item for item in goals if item.slot is Slot.SANDS)

        self.assertEqual(preset.constellation, 2)
        self.assertEqual(preset.weapon, "WolfsGravestone")
        self.assertEqual(len(sands.allowed_main_stats), 2)
        self.assertEqual(len(set(sands.main_stat_priorities.values())), 1)

    def test_analyzes_good_without_requiring_equipped_artifacts(self) -> None:
        payload = {
            "format": "GOOD",
            "version": 1,
            "source": "Test",
            "artifacts": [
                good_artifact("flower", "hp", ["critRate_", "critDMG_"]),
                good_artifact("plume", "atk", ["critRate_", "critDMG_"]),
                good_artifact("sands", "atk_", ["critRate_", "critDMG_"]),
                good_artifact("goblet", "pyro_dmg_", ["critRate_", "critDMG_"]),
                good_artifact("circlet", "critRate_", ["critDMG_", "atk_"]),
            ],
        }

        result = analyze_mavuika_inventory(payload)

        self.assertEqual(result.inventory.artifacts, 5)
        self.assertEqual(result.inventory.equipped_artifacts, 0)
        self.assertTrue(result.audit.starter_build_available)
        self.assertEqual(result.audit.pending_slots, [])
        self.assertEqual(set(result.audit.selected_artifact_ids), set(Slot))

    def test_empty_good_fails_loudly(self) -> None:
        payload = {
            "format": "GOOD",
            "version": 1,
            "source": "Test",
            "artifacts": [],
        }

        with self.assertRaisesRegex(ValueError, "no artifacts"):
            analyze_mavuika_inventory(payload)

    def test_simulation_uses_inventory_baseline_without_fake_enhancement(self) -> None:
        payload = {
            "format": "GOOD",
            "version": 1,
            "source": "Test",
            "artifacts": [
                good_artifact("flower", "hp", ["critRate_", "critDMG_"]),
                good_artifact("plume", "atk", ["critRate_", "critDMG_"]),
                good_artifact("sands", "atk_", ["critRate_", "critDMG_"]),
                good_artifact("goblet", "pyro_dmg_", ["critRate_", "critDMG_"]),
                good_artifact("circlet", "critRate_", ["critDMG_", "atk_"]),
            ],
        }
        request = MavuikaFarmSimulationRequest(
            inventory=payload,
            policy=FarmPolicy.SPEND_ALL,
            target_slots=[Slot.SANDS, Slot.GOBLET, Slot.CIRCLET],
            resin_budget=200,
            seed=42,
        )

        simulation = simulate_mavuika_farm(request)

        self.assertEqual(simulation.result.runs, 10)
        self.assertEqual(simulation.result.resin_spent, 200)
        self.assertEqual(simulation.result.model_checkpoints, 1)
        self.assertEqual(len(simulation.runs), 10)
        self.assertFalse(any(item.level > 0 for item in simulation.result.collected_artifacts))
        self.assertTrue(all(not run.analyzed for run in simulation.runs[:-1]))
        self.assertTrue(simulation.runs[-1].analyzed)

    def test_simulation_supports_a_partial_provisional_baseline(self) -> None:
        payload = {
            "format": "GOOD",
            "version": 1,
            "source": "Test",
            "artifacts": [good_artifact("flower", "hp", ["critRate_", "critDMG_"])],
        }

        simulation = simulate_mavuika_farm(
            MavuikaFarmSimulationRequest(
                inventory=payload,
                policy=FarmPolicy.SPEND_ALL,
                target_slots=[Slot.SANDS],
                resin_budget=20,
                seed=7,
            )
        )

        self.assertEqual(set(simulation.baseline_artifact_ids), {Slot.FLOWER})
        self.assertIsNone(simulation.result.slot_progress[0].baseline_artifact_id)
        started = next(
            event for event in simulation.result.trace if event.event == "session_started"
        )
        self.assertIn("sands", started.details["empty_baseline_slots"])

    def test_simulation_supports_inventory_without_any_target_set(self) -> None:
        payload = {
            "format": "GOOD",
            "version": 1,
            "source": "Test",
            "artifacts": [
                good_artifact("flower", "hp", ["critRate_", "critDMG_"], "GladiatorsFinale"),
                good_artifact("plume", "atk", ["critRate_", "critDMG_"], "GladiatorsFinale"),
                good_artifact("sands", "atk_", ["critRate_", "critDMG_"], "GladiatorsFinale"),
                good_artifact("goblet", "pyro_dmg_", ["critRate_", "critDMG_"], "GladiatorsFinale"),
                good_artifact("circlet", "critRate_", ["critDMG_", "atk_"], "GladiatorsFinale"),
            ],
        }

        simulation = simulate_mavuika_farm(
            MavuikaFarmSimulationRequest(
                inventory=payload,
                policy=FarmPolicy.SPEND_ALL,
                target_slots=list(Slot),
                resin_budget=20,
                seed=9,
            )
        )

        self.assertEqual(set(simulation.baseline_artifact_ids), set(Slot))
        self.assertEqual(simulation.result.runs, 1)
        self.assertTrue(all(item.baseline_artifact_id for item in simulation.result.slot_progress))


if __name__ == "__main__":
    unittest.main()
