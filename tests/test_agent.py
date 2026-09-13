from __future__ import annotations

import unittest

from grindless.agent import GrindLessAgent
from grindless.fixtures import xiangling_account, xiangling_goal
from grindless.models import (
    AccountState,
    Artifact,
    CharacterProfile,
    Decision,
    EnhancementAuthorization,
    EnhancementResult,
    FarmPolicy,
    GuaranteedUpgrade,
    RewardBatch,
    Slot,
    Stat,
    StopReason,
    Substat,
)
from grindless.optimizer import BruteForceBuildOptimizer


class ScriptedAdapter:
    def __init__(self, batches: list[RewardBatch], resin: int = 200) -> None:
        self.batches = list(batches)
        self._resin = resin
        self.claims = 0
        self.enhancements = 0

    @property
    def resin_remaining(self) -> int:
        return self._resin

    def claim_reward(self, cost: int) -> RewardBatch:
        if self._resin < cost:
            raise ValueError("not enough resin")
        if not self.batches:
            raise AssertionError("unexpected extra claim")
        self._resin -= cost
        self.claims += 1
        return self.batches.pop(0)

    def enhance_artifact(self, artifact: Artifact, target_level: int = 20) -> EnhancementResult:
        self.enhancements += 1
        if artifact.level != target_level:
            artifact = artifact.model_copy(update={"level": target_level})
        return EnhancementResult(artifact=artifact, events=[])


def reward(run: int, *artifacts: Artifact, confidence: float = 1.0) -> RewardBatch:
    return RewardBatch(
        run_number=run,
        artifacts=list(artifacts),
        resin_spent=20,
        observation_confidence=confidence,
    )


def strong_artifact(artifact_id: str, slot: Slot) -> Artifact:
    main_stat = Stat.ATK_FLAT if slot == Slot.PLUME else Stat.CRIT_RATE
    main_value = 311.0 if slot == Slot.PLUME else 31.1
    substats = [
        Substat(stat=Stat.CRIT_DMG, value=31.2),
        Substat(stat=Stat.ENERGY_RECHARGE, value=18.1),
        Substat(stat=Stat.ATK_PCT, value=11.6),
    ]
    if main_stat != Stat.CRIT_RATE:
        substats.append(Substat(stat=Stat.CRIT_RATE, value=10.5))
    else:
        substats.append(Substat(stat=Stat.ELEMENTAL_MASTERY, value=23.0))
    return Artifact(
        id=artifact_id,
        set_name="EmblemOfSeveredFate",
        slot=slot,
        level=0,
        main_stat=main_stat,
        main_value=main_value,
        substats=substats,
    )


def irrelevant_artifact(artifact_id: str) -> Artifact:
    return Artifact(
        id=artifact_id,
        set_name="ShimenawasReminiscence",
        slot=Slot.FLOWER,
        level=0,
        main_stat=Stat.HP_FLAT,
        main_value=717.0,
        substats=[Substat(stat=Stat.DEF_FLAT, value=23.0)],
    )


class GrindLessAgentTests(unittest.TestCase):
    def test_economy_accepts_first_candidate_for_an_empty_baseline_slot(self) -> None:
        goal = xiangling_goal(FarmPolicy.ECONOMY).model_copy(
            update={"targets": [xiangling_goal(FarmPolicy.ECONOMY).targets[0]]}
        )
        adapter = ScriptedAdapter(
            [reward(1, strong_artifact("first-plume", Slot.PLUME))],
            resin=20,
        )

        result = GrindLessAgent().run(
            state=AccountState(
                character=CharacterProfile(name="Xiangling"),
                artifacts=[],
            ),
            goal=goal,
            adapter=adapter,
        )

        self.assertEqual(result.reason, StopReason.ALL_SLOT_GOALS_MET)
        self.assertIsNone(result.slot_progress[0].baseline_artifact_id)
        self.assertEqual(result.slot_progress[0].best_artifact_id, "first-plume")
        self.assertTrue(result.slot_progress[0].accepted)
        self.assertEqual(set(result.best_build.artifacts), {Slot.PLUME})

    def test_empty_baseline_does_not_accept_a_wrong_set_as_first_piece(self) -> None:
        goal = xiangling_goal(FarmPolicy.ECONOMY).model_copy(
            update={"targets": [xiangling_goal(FarmPolicy.ECONOMY).targets[0]]}
        )
        wrong_set = strong_artifact("wrong-set", Slot.PLUME).model_copy(
            update={"set_name": "ShimenawasReminiscence"}
        )
        adapter = ScriptedAdapter(
            [
                reward(1, wrong_set),
                reward(2, strong_artifact("first-valid", Slot.PLUME)),
            ],
            resin=40,
        )

        result = GrindLessAgent().run(
            state=AccountState(
                character=CharacterProfile(name="Xiangling"),
                artifacts=[],
            ),
            goal=goal,
            adapter=adapter,
        )

        self.assertEqual(result.runs, 2)
        self.assertEqual(result.slot_progress[0].best_artifact_id, "first-valid")
        first_evaluation = next(
            event
            for event in result.trace
            if event.event == "artifact_evaluated"
            and event.details["artifact_id"] == "wrong-set"
        )
        self.assertFalse(first_evaluation.details["promising"])

    def test_content_comparison_ignores_substat_numbers(self) -> None:
        state = xiangling_account()
        candidate = Artifact(
            id="same-types-huge-values",
            set_name="EmblemOfSeveredFate",
            slot=Slot.PLUME,
            level=0,
            main_stat=Stat.ATK_FLAT,
            main_value=47.0,
            substats=[
                Substat(stat=Stat.CRIT_RATE, value=99.0),
                Substat(stat=Stat.CRIT_DMG, value=99.0),
                Substat(stat=Stat.ENERGY_RECHARGE, value=99.0),
            ],
        )
        state.artifacts.append(candidate)
        goal = xiangling_goal(FarmPolicy.ECONOMY).model_copy(
            update={"targets": [xiangling_goal(FarmPolicy.ECONOMY).targets[0]]}
        )
        optimizer = BruteForceBuildOptimizer()

        progress = optimizer.assess_targets(state, state.equipped_build(), goal)

        self.assertFalse(progress[0].accepted)
        self.assertEqual(progress[0].baseline_content_score, progress[0].candidate_content_score)

    def test_content_optimizer_can_move_the_off_piece_between_target_slots(self) -> None:
        state = xiangling_account()
        baseline_circlet = state.artifact_by_id("base-circlet").model_copy(
            update={"set_name": "ShimenawasReminiscence"}
        )
        state.artifacts = [
            baseline_circlet if item.id == baseline_circlet.id else item
            for item in state.artifacts
        ]
        state.artifacts.extend([
            strong_artifact("set-circlet", Slot.CIRCLET),
            strong_artifact("off-plume", Slot.PLUME).model_copy(
                update={"set_name": "ShimenawasReminiscence"}
            ),
        ])

        progress = BruteForceBuildOptimizer().assess_targets(
            state,
            state.equipped_build(),
            xiangling_goal(FarmPolicy.ECONOMY),
        )

        by_slot = {item.slot: item for item in progress}
        self.assertEqual(by_slot[Slot.PLUME].best_artifact_id, "off-plume")
        self.assertEqual(by_slot[Slot.CIRCLET].best_artifact_id, "set-circlet")
        self.assertTrue(by_slot[Slot.PLUME].accepted)
        self.assertTrue(by_slot[Slot.CIRCLET].accepted)

    def test_economy_stops_when_every_target_slot_is_improved(self) -> None:
        adapter = ScriptedAdapter(
            [
                reward(1, strong_artifact("new-plume", Slot.PLUME)),
                reward(2, strong_artifact("new-circlet", Slot.CIRCLET)),
                reward(3, irrelevant_artifact("must-not-be-claimed")),
            ],
        )

        result = GrindLessAgent().run(
            state=xiangling_account(),
            goal=xiangling_goal(FarmPolicy.ECONOMY),
            adapter=adapter,
        )

        self.assertEqual(result.reason, StopReason.ALL_SLOT_GOALS_MET)
        self.assertEqual(result.decision, Decision.STOP)
        self.assertEqual(result.runs, 2)
        self.assertEqual(result.resin_spent, 40)
        self.assertEqual(result.resin_remaining, 160)
        self.assertEqual(result.model_checkpoints, 3)
        self.assertTrue(all(item.accepted for item in result.slot_progress))
        self.assertEqual(adapter.enhancements, 0)
        self.assertTrue(all(item.level == 0 for item in result.collected_artifacts))
        self.assertTrue(
            all(item.evaluation_mode == "content_only" for item in result.slot_progress)
        )

    def test_spend_all_uses_ten_claims_even_after_early_improvements(self) -> None:
        batches = [
            reward(1, strong_artifact("new-plume", Slot.PLUME), strong_artifact("new-circlet", Slot.CIRCLET))
        ] + [reward(index, irrelevant_artifact(f"drop-{index}")) for index in range(2, 11)]
        adapter = ScriptedAdapter(batches)

        result = GrindLessAgent().run(
            state=xiangling_account(),
            goal=xiangling_goal(FarmPolicy.SPEND_ALL),
            adapter=adapter,
        )

        self.assertEqual(result.reason, StopReason.FULL_BUDGET_SPENT)
        self.assertEqual(result.runs, 10)
        self.assertEqual(adapter.claims, 10)
        self.assertEqual(result.resin_spent, 200)
        self.assertEqual(result.model_checkpoints, 1)
        self.assertTrue(all(item.accepted for item in result.slot_progress))
        self.assertEqual(adapter.enhancements, 0)

    def test_explicit_authorization_enables_bounded_enhancement(self) -> None:
        goal = xiangling_goal(FarmPolicy.ECONOMY).model_copy(
            update={
                "enhancement": EnhancementAuthorization(
                    enabled=True,
                    max_artifacts=1,
                    target_level=20,
                )
            }
        )
        adapter = ScriptedAdapter(
            [
                reward(
                    1,
                    strong_artifact("new-plume", Slot.PLUME),
                    strong_artifact("new-circlet", Slot.CIRCLET),
                )
            ],
            resin=20,
        )

        result = GrindLessAgent().run(
            state=xiangling_account(),
            goal=goal,
            adapter=adapter,
        )

        self.assertEqual(adapter.enhancements, 1)
        self.assertEqual(
            sum(item.level == 20 for item in result.collected_artifacts),
            1,
        )
        self.assertTrue(
            all(item.evaluation_mode == "enhanced_values" for item in result.slot_progress)
        )

    def test_economy_changes_goal_when_guaranteed_upgrade_is_better(self) -> None:
        goal = xiangling_goal(FarmPolicy.ECONOMY).model_copy(
            update={
                "configured_artifact_gain_per_resin": 0.0001,
                "alternative_upgrade": GuaranteedUpgrade(
                    name="уровень таланта",
                    expected_gain=0.03,
                    resin_cost=20,
                ),
            }
        )
        adapter = ScriptedAdapter([reward(1, irrelevant_artifact("unused"))])

        result = GrindLessAgent().run(
            state=xiangling_account(),
            goal=goal,
            adapter=adapter,
        )

        self.assertEqual(result.decision, Decision.CHANGE_GOAL)
        self.assertEqual(result.reason, StopReason.GUARANTEED_UPGRADE_IS_BETTER)
        self.assertEqual(result.runs, 0)
        self.assertEqual(adapter.claims, 0)

    def test_low_confidence_causes_safe_stop_and_accounts_for_resin(self) -> None:
        adapter = ScriptedAdapter(
            [reward(1, irrelevant_artifact("uncertain"), confidence=0.80)]
        )

        result = GrindLessAgent().run(
            state=xiangling_account(),
            goal=xiangling_goal(FarmPolicy.ECONOMY),
            adapter=adapter,
        )

        self.assertEqual(result.decision, Decision.SAFE_STOP)
        self.assertEqual(result.reason, StopReason.UNKNOWN_STATE)
        self.assertEqual(result.runs, 1)
        self.assertEqual(result.resin_spent, 20)
        self.assertEqual(result.resin_remaining, 180)


if __name__ == "__main__":
    unittest.main()
