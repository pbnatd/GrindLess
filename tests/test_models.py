from __future__ import annotations

import unittest

from pydantic import ValidationError

from grindless.models import (
    Artifact,
    ArtifactSetRequirement,
    BuildConstraints,
    EnhancementAuthorization,
    FarmGoal,
    FarmPolicy,
    Slot,
    SlotGoal,
    Stat,
    Substat,
)
from grindless.fixtures import xiangling_goal


class ModelValidationTests(unittest.TestCase):
    def test_main_stat_cannot_be_repeated_as_substat(self) -> None:
        with self.assertRaises(ValidationError):
            Artifact(
                id="invalid",
                set_name="Example",
                slot=Slot.CIRCLET,
                main_stat=Stat.CRIT_RATE,
                main_value=4.7,
                substats=[Substat(stat=Stat.CRIT_RATE, value=3.1)],
            )

    def test_target_slots_must_be_unique(self) -> None:
        original = xiangling_goal(FarmPolicy.ECONOMY)
        payload = original.model_dump()
        payload["targets"] = [
            SlotGoal(slot=Slot.PLUME),
            SlotGoal(slot=Slot.PLUME),
        ]
        with self.assertRaises(ValidationError):
            FarmGoal.model_validate(payload)

    def test_enhancement_permission_requires_a_positive_budget(self) -> None:
        with self.assertRaises(ValidationError):
            EnhancementAuthorization(enabled=True, max_artifacts=0)

    def test_set_composition_accepts_four_piece_or_two_plus_two(self) -> None:
        four_piece = BuildConstraints(
            stat_weights={},
            set_requirements=[ArtifactSetRequirement(set_name="SetA", pieces=4)],
        )
        mixed = BuildConstraints(
            stat_weights={},
            set_requirements=[
                ArtifactSetRequirement(set_name="SetA", pieces=2),
                ArtifactSetRequirement(set_name="SetB", pieces=2),
            ],
        )
        self.assertEqual(sum(item.pieces for item in four_piece.set_requirements), 4)
        self.assertEqual(sum(item.pieces for item in mixed.set_requirements), 4)

    def test_set_composition_rejects_duplicate_or_partial_requirements(self) -> None:
        with self.assertRaises(ValidationError):
            BuildConstraints(
                stat_weights={},
                set_requirements=[ArtifactSetRequirement(set_name="SetA", pieces=2)],
            )
        with self.assertRaises(ValidationError):
            BuildConstraints(
                stat_weights={},
                set_requirements=[
                    ArtifactSetRequirement(set_name="SetA", pieces=2),
                    ArtifactSetRequirement(set_name="SetA", pieces=2),
                ],
            )


if __name__ == "__main__":
    unittest.main()
