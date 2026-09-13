from __future__ import annotations

import unittest

from grindless.fixtures import mavuika_goal
from grindless.models import (
    Artifact,
    ArtifactSetRequirement,
    BuildConstraints,
    FarmPolicy,
    Slot,
    Stat,
    Substat,
)
from grindless.optimizer import BruteForceBuildOptimizer


def artifact(
    artifact_id: str,
    slot: Slot,
    main_stat: Stat,
    substats: list[tuple[Stat, float]],
    source_index: int,
    set_name: str = "ObsidianCodex",
) -> Artifact:
    return Artifact(
        id=artifact_id,
        set_name=set_name,
        slot=slot,
        level=0,
        main_stat=main_stat,
        substats=[Substat(stat=stat, value=value) for stat, value in substats],
        source="test",
        source_index=source_index,
    )


class InitialBuildAuditTests(unittest.TestCase):
    def test_mavuika_preset_records_declared_context(self) -> None:
        goal = mavuika_goal(FarmPolicy.ECONOMY)

        self.assertEqual(goal.build_context.constellation, 2)
        self.assertEqual(goal.build_context.weapon_refinement, 1)
        self.assertEqual(
            goal.build_context.target_team,
            ["Mavuika", "Citlali", "Xilonen", "Bennett"],
        )

    def test_empty_baseline_audit_does_not_require_equipped_artifacts(self) -> None:
        items = [
            artifact("flower", Slot.FLOWER, Stat.HP_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.ELEMENTAL_MASTERY, 23)], 1),
            artifact("plume", Slot.PLUME, Stat.ATK_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 2),
            artifact("sands", Slot.SANDS, Stat.ELEMENTAL_MASTERY, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 3),
            artifact("goblet", Slot.GOBLET, Stat.ATK_PCT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 4),
            artifact("circlet", Slot.CIRCLET, Stat.CRIT_RATE, [(Stat.CRIT_DMG, 7.8), (Stat.ELEMENTAL_MASTERY, 23)], 5),
        ]

        audit = BruteForceBuildOptimizer().audit_initial_build(
            items, mavuika_goal(FarmPolicy.ECONOMY)
        )

        self.assertTrue(audit.starter_build_available)
        self.assertEqual(audit.pending_slots, [Slot.GOBLET])
        self.assertFalse(audit.candidates[Slot.GOBLET][0].closes_goal)

    def test_numeric_substat_values_do_not_break_content_ties(self) -> None:
        low = artifact(
            "low",
            Slot.SANDS,
            Stat.ATK_PCT,
            [(Stat.CRIT_RATE, 2.7), (Stat.CRIT_DMG, 5.4)],
            1,
        )
        high = artifact(
            "high",
            Slot.SANDS,
            Stat.ATK_PCT,
            [(Stat.CRIT_RATE, 99), (Stat.CRIT_DMG, 99)],
            2,
        )

        audit = BruteForceBuildOptimizer().audit_initial_build(
            [low, high], mavuika_goal(FarmPolicy.ECONOMY)
        )

        candidates = audit.candidates[Slot.SANDS]
        self.assertEqual(candidates[0].content_score, candidates[1].content_score)
        self.assertEqual(candidates[0].artifact_id, "low")

    def test_atk_and_em_sands_have_equal_main_stat_priority(self) -> None:
        atk = artifact("atk", Slot.SANDS, Stat.ATK_PCT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 1)
        em = artifact("em", Slot.SANDS, Stat.ELEMENTAL_MASTERY, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 2)

        audit = BruteForceBuildOptimizer().audit_initial_build(
            [atk, em], mavuika_goal(FarmPolicy.ECONOMY)
        )

        self.assertEqual(
            audit.candidates[Slot.SANDS][0].main_stat_priority,
            audit.candidates[Slot.SANDS][1].main_stat_priority,
        )

    def test_four_piece_build_chooses_best_off_piece_from_any_set(self) -> None:
        items = [
            artifact("flower", Slot.FLOWER, Stat.HP_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 1),
            artifact("plume", Slot.PLUME, Stat.ATK_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 2),
            artifact("sands", Slot.SANDS, Stat.ATK_PCT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 3),
            artifact("goblet", Slot.GOBLET, Stat.PYRO_DMG, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 4),
            artifact("set-circlet", Slot.CIRCLET, Stat.CRIT_RATE, [(Stat.ATK_PCT, 5.8)], 5),
            artifact("off-circlet", Slot.CIRCLET, Stat.CRIT_RATE, [(Stat.CRIT_DMG, 7.8), (Stat.ELEMENTAL_MASTERY, 23)], 6, "GoldenTroupe"),
        ]

        audit = BruteForceBuildOptimizer().audit_initial_build(
            items, mavuika_goal(FarmPolicy.ECONOMY)
        )

        self.assertTrue(audit.set_composition_met)
        self.assertTrue(audit.starter_build_available)
        self.assertEqual(audit.selected_artifact_ids[Slot.CIRCLET], "off-circlet")
        self.assertEqual(audit.off_piece_artifact_id, "off-circlet")
        self.assertEqual(audit.selected_set_counts["ObsidianCodex"], 4)

    def test_two_plus_two_is_selected_as_one_coherent_build(self) -> None:
        goal = mavuika_goal(FarmPolicy.ECONOMY).model_copy(
            update={
                "constraints": BuildConstraints(
                    stat_weights={},
                    set_requirements=[
                        ArtifactSetRequirement(set_name="SetA", pieces=2),
                        ArtifactSetRequirement(set_name="SetB", pieces=2),
                    ],
                )
            }
        )
        items = [
            artifact("a-flower", Slot.FLOWER, Stat.HP_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 1, "SetA"),
            artifact("a-plume", Slot.PLUME, Stat.ATK_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 2, "SetA"),
            artifact("b-sands", Slot.SANDS, Stat.ATK_PCT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 3, "SetB"),
            artifact("b-goblet", Slot.GOBLET, Stat.PYRO_DMG, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 4, "SetB"),
            artifact("flex-circlet", Slot.CIRCLET, Stat.CRIT_RATE, [(Stat.CRIT_DMG, 7.8), (Stat.ELEMENTAL_MASTERY, 23)], 5, "SetC"),
        ]

        audit = BruteForceBuildOptimizer().audit_initial_build(items, goal)

        self.assertTrue(audit.set_composition_met)
        self.assertEqual(audit.selected_set_counts, {"SetA": 2, "SetB": 2, "SetC": 1})
        self.assertEqual(audit.off_piece_artifact_id, "flex-circlet")

    def test_missing_set_composition_blocks_a_false_complete_build(self) -> None:
        goal = mavuika_goal(FarmPolicy.ECONOMY).model_copy(
            update={
                "constraints": BuildConstraints(
                    stat_weights={},
                    set_requirements=[
                        ArtifactSetRequirement(set_name="SetA", pieces=2),
                        ArtifactSetRequirement(set_name="SetB", pieces=2),
                    ],
                )
            }
        )
        items = [
            artifact("flower", Slot.FLOWER, Stat.HP_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 1, "SetA"),
            artifact("plume", Slot.PLUME, Stat.ATK_FLAT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 2, "SetA"),
            artifact("sands", Slot.SANDS, Stat.ATK_PCT, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 3, "SetA"),
            artifact("goblet", Slot.GOBLET, Stat.PYRO_DMG, [(Stat.CRIT_RATE, 3.1), (Stat.CRIT_DMG, 7.8)], 4, "SetA"),
            artifact("circlet", Slot.CIRCLET, Stat.CRIT_RATE, [(Stat.CRIT_DMG, 7.8), (Stat.ELEMENTAL_MASTERY, 23)], 5, "SetC"),
        ]

        audit = BruteForceBuildOptimizer().audit_initial_build(items, goal)

        self.assertFalse(audit.set_composition_met)
        self.assertFalse(audit.starter_build_available)
        self.assertIsNone(audit.off_piece_artifact_id)


if __name__ == "__main__":
    unittest.main()
