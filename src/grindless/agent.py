from __future__ import annotations

from .models import (
    AccountState,
    Artifact,
    Build,
    Decision,
    FarmGoal,
    FarmPolicy,
    FarmSessionResult,
    RewardBatch,
    Slot,
    SlotProgress,
    StopReason,
    TraceEvent,
)
from .narrator import TemplateNarrator
from .optimizer import BruteForceBuildOptimizer
from .ports import FarmAdapter, Narrator
from .stop_policy import ConfiguredExpectedGainEstimator


class GrindLessAgent:
    """Closed-loop agent whose environment is selected through FarmAdapter."""

    MIN_OBSERVATION_CONFIDENCE = 0.95

    def __init__(
        self,
        *,
        optimizer: BruteForceBuildOptimizer | None = None,
        estimator: ConfiguredExpectedGainEstimator | None = None,
        narrator: Narrator | None = None,
    ) -> None:
        self.optimizer = optimizer or BruteForceBuildOptimizer()
        self.estimator = estimator or ConfiguredExpectedGainEstimator()
        self.narrator = narrator or TemplateNarrator()

    def run(
        self,
        *,
        state: AccountState,
        goal: FarmGoal,
        adapter: FarmAdapter,
    ) -> FarmSessionResult:
        if state.character.name != goal.character:
            raise ValueError("goal character does not match account state")

        working_state = state.model_copy(deep=True)
        initial_resin = adapter.resin_remaining
        baseline = self.optimizer.evaluate(working_state.equipped_build(), goal)
        trace = [
            TraceEvent(
                event="session_started",
                details={
                    "policy": goal.policy.value,
                    "resin_budget": goal.resin_budget,
                    "adapter_resin": initial_resin,
                    "target_slots": [target.slot.value for target in goal.targets],
                    "baseline_score": baseline.score,
                    "baseline_artifact_ids": {
                        slot.value: artifact.id
                        for slot, artifact in baseline.artifacts.items()
                    },
                    "empty_baseline_slots": [
                        slot.value for slot in Slot if slot not in baseline.artifacts
                    ],
                    "evaluation_mode": (
                        "enhanced_values" if goal.enhancement.enabled else "content_only"
                    ),
                    "enhancement_authorized": goal.enhancement.enabled,
                    "enhancement_limit": goal.enhancement.max_artifacts,
                },
            )
        ]
        collected: list[Artifact] = []
        enhancement_budget = [goal.enhancement.max_artifacts]

        if self.estimator.should_change_goal(working_state, goal):
            trace.append(
                TraceEvent(
                    event="goal_changed_before_farm",
                    details={"alternative": goal.alternative_upgrade.name},
                )
            )
            return self._result(
                state=working_state,
                baseline=baseline,
                goal=goal,
                adapter=adapter,
                decision=Decision.CHANGE_GOAL,
                reason=StopReason.GUARANTEED_UPGRADE_IS_BETTER,
                runs=0,
                spent=0,
                checkpoints=1,
                collected=collected,
                trace=trace,
            )

        run_limit = min(
            goal.resin_budget // goal.reward_cost,
            adapter.resin_remaining // goal.reward_cost,
        )
        if run_limit == 0:
            return self._result(
                state=working_state,
                baseline=baseline,
                goal=goal,
                adapter=adapter,
                decision=Decision.STOP,
                reason=StopReason.RESIN_EXHAUSTED,
                runs=0,
                spent=0,
                checkpoints=1,
                collected=collected,
                trace=trace,
            )

        if goal.policy == FarmPolicy.SPEND_ALL:
            batches: list[RewardBatch] = []
            for _ in range(run_limit):
                batch = adapter.claim_reward(goal.reward_cost)
                safe_reason = self._validate_batch(batch)
                if safe_reason:
                    trace.append(
                        TraceEvent(
                            event="safe_stop",
                            details={"run": batch.run_number, "reason": safe_reason.value},
                        )
                    )
                    return self._result(
                        state=working_state,
                        baseline=baseline,
                        goal=goal,
                        adapter=adapter,
                        decision=Decision.SAFE_STOP,
                        reason=safe_reason,
                        runs=len(batches) + 1,
                        spent=initial_resin - adapter.resin_remaining,
                        checkpoints=1,
                        collected=collected,
                        trace=trace,
                    )
                batches.append(batch)
                collected.extend(batch.artifacts)
                trace.append(
                    TraceEvent(
                        event="reward_staged_without_analysis",
                        details={
                            "run": batch.run_number,
                            "artifact_count": len(batch.artifacts),
                            "artifact_ids": [item.id for item in batch.artifacts],
                        },
                    )
                )

            collected = self._analyze_batches(
                working_state, goal, adapter, batches, trace, enhancement_budget
            )
            return self._result(
                state=working_state,
                baseline=baseline,
                goal=goal,
                adapter=adapter,
                decision=Decision.STOP,
                reason=StopReason.FULL_BUDGET_SPENT,
                runs=len(batches),
                spent=sum(item.resin_spent for item in batches),
                checkpoints=1,
                collected=collected,
                trace=trace,
            )

        model_checkpoints = 0
        spent = 0
        completed_runs = 0
        for _ in range(run_limit):
            batch = adapter.claim_reward(goal.reward_cost)
            safe_reason = self._validate_batch(batch)
            if safe_reason:
                trace.append(
                    TraceEvent(
                        event="safe_stop",
                        details={"run": batch.run_number, "reason": safe_reason.value},
                    )
                )
                return self._result(
                    state=working_state,
                    baseline=baseline,
                    goal=goal,
                    adapter=adapter,
                    decision=Decision.SAFE_STOP,
                    reason=safe_reason,
                    runs=completed_runs + 1,
                    spent=initial_resin - adapter.resin_remaining,
                    checkpoints=model_checkpoints + 1,
                    collected=collected,
                    trace=trace,
                )

            completed_runs += 1
            spent += batch.resin_spent
            analyzed = self._analyze_batches(
                working_state, goal, adapter, [batch], trace, enhancement_budget
            )
            collected.extend(analyzed)
            progress = self.optimizer.assess_targets(working_state, baseline, goal)
            checkpoint_text = self.narrator.checkpoint(batch.run_number, progress)
            model_checkpoints += 1
            trace.append(
                TraceEvent(
                    event="checkpoint",
                    details={
                        "run": batch.run_number,
                        "accepted_slots": [item.slot.value for item in progress if item.accepted],
                        "narration": checkpoint_text,
                    },
                )
            )

            if all(item.accepted for item in progress):
                return self._result(
                    state=working_state,
                    baseline=baseline,
                    goal=goal,
                    adapter=adapter,
                    decision=Decision.STOP,
                    reason=StopReason.ALL_SLOT_GOALS_MET,
                    runs=completed_runs,
                    spent=spent,
                    checkpoints=model_checkpoints + 1,
                    collected=collected,
                    trace=trace,
                )

            if self.estimator.should_change_goal(working_state, goal, progress):
                trace.append(
                    TraceEvent(
                        event="goal_changed_after_checkpoint",
                        details={"alternative": goal.alternative_upgrade.name},
                    )
                )
                return self._result(
                    state=working_state,
                    baseline=baseline,
                    goal=goal,
                    adapter=adapter,
                    decision=Decision.CHANGE_GOAL,
                    reason=StopReason.GUARANTEED_UPGRADE_IS_BETTER,
                    runs=completed_runs,
                    spent=spent,
                    checkpoints=model_checkpoints + 1,
                    collected=collected,
                    trace=trace,
                )

        return self._result(
            state=working_state,
            baseline=baseline,
            goal=goal,
            adapter=adapter,
            decision=Decision.STOP,
            reason=StopReason.RESIN_EXHAUSTED,
            runs=completed_runs,
            spent=spent,
            checkpoints=model_checkpoints + 1,
            collected=collected,
            trace=trace,
        )

    def _analyze_batches(
        self,
        state: AccountState,
        goal: FarmGoal,
        adapter: FarmAdapter,
        batches: list[RewardBatch],
        trace: list[TraceEvent],
        enhancement_budget: list[int],
    ) -> list[Artifact]:
        analyzed: list[Artifact] = []
        targets = {target.slot: target for target in goal.targets}
        for batch in batches:
            for raw in batch.artifacts:
                artifact = raw
                target = targets.get(raw.slot)
                relevant = target is not None and self.optimizer.content_eligible(
                    raw, target, state
                )
                promising = False
                if relevant:
                    score, matched = self.optimizer.content_score(raw, target)
                    equipped_build = state.equipped_build()
                    baseline_artifact = equipped_build.artifacts.get(raw.slot)
                    baseline_score = (
                        self.optimizer.content_score(baseline_artifact, target)[0]
                        if baseline_artifact is not None
                        else 0.0
                    )
                    baseline_eligible = (
                        baseline_artifact is not None
                        and self.optimizer.content_eligible(
                            baseline_artifact, target, state
                        )
                        and self.optimizer.set_requirements_met(
                            equipped_build.artifacts.values(), goal
                        )
                    )
                    required_sets = {
                        requirement.set_name
                        for requirement in goal.constraints.set_requirements
                    }
                    candidate_advances_composition = (
                        not required_sets or raw.set_name in required_sets
                    )
                    promising = (
                        len(matched) >= target.min_useful_substats
                        and (baseline_eligible or candidate_advances_composition)
                        and (
                            not baseline_eligible
                            or score - baseline_score >= target.min_content_score_gain
                        )
                    )

                evaluation_details: dict[str, object] = {
                    "run": batch.run_number,
                    "artifact_id": raw.id,
                    "slot": raw.slot.value,
                    "set_name": raw.set_name,
                    "main_stat": raw.main_stat.value,
                    "relevant": relevant,
                    "promising": promising,
                }
                if relevant and target is not None:
                    evaluation_details.update(
                        {
                            "content_score": score,
                            "baseline_content_score": baseline_score,
                            "baseline_eligible": baseline_eligible,
                            "candidate_advances_composition": (
                                candidate_advances_composition
                            ),
                            "matched_substats": [item.value for item in matched],
                            "required_useful_substats": target.min_useful_substats,
                            "required_score_gain": target.min_content_score_gain,
                        }
                    )
                trace.append(
                    TraceEvent(event="artifact_evaluated", details=evaluation_details)
                )

                if (
                    promising
                    and goal.enhancement.enabled
                    and enhancement_budget[0] > 0
                ):
                    outcome = adapter.enhance_artifact(
                        raw, target_level=goal.enhancement.target_level
                    )
                    artifact = outcome.artifact
                    enhancement_budget[0] -= 1
                    trace.append(
                        TraceEvent(
                            event="artifact_enhanced",
                            details={
                                "run": batch.run_number,
                                "artifact_id": artifact.id,
                                "slot": artifact.slot.value,
                                "levels": [event.to_level for event in outcome.events],
                                "authorized_limit_remaining": enhancement_budget[0],
                            },
                        )
                    )
                else:
                    if not goal.enhancement.enabled:
                        reason = "content-only mode: enhancement was not authorized"
                    elif not relevant:
                        reason = "outside declared slot/main-stat/set target"
                    elif not promising:
                        reason = "substat content is not better than the baseline"
                    else:
                        reason = "authorized enhancement limit is exhausted"
                    trace.append(
                        TraceEvent(
                            event="artifact_not_enhanced",
                            details={
                                "run": batch.run_number,
                                "artifact_id": artifact.id,
                                "slot": artifact.slot.value,
                                "reason": reason,
                            },
                        )
                    )
                self._upsert_artifact(state, artifact)
                analyzed.append(artifact)
        return analyzed

    @staticmethod
    def _validate_batch(batch: RewardBatch) -> StopReason | None:
        if batch.observation_confidence < GrindLessAgent.MIN_OBSERVATION_CONFIDENCE:
            return StopReason.UNKNOWN_STATE
        if not batch.reward_confirmed:
            return StopReason.REWARD_NOT_CONFIRMED
        return None

    @staticmethod
    def _upsert_artifact(state: AccountState, artifact: Artifact) -> None:
        for index, existing in enumerate(state.artifacts):
            if existing.id == artifact.id:
                state.artifacts[index] = artifact
                return
        state.artifacts.append(artifact)

    def _result(
        self,
        *,
        state: AccountState,
        baseline: Build,
        goal: FarmGoal,
        adapter: FarmAdapter,
        decision: Decision,
        reason: StopReason,
        runs: int,
        spent: int,
        checkpoints: int,
        collected: list[Artifact],
        trace: list[TraceEvent],
    ) -> FarmSessionResult:
        progress = self.optimizer.assess_targets(state, baseline, goal)
        # Select exactly the accepted per-slot evidence. In content-only mode
        # this prevents numeric +0 values from leaking into the decision.
        selected = dict(baseline.artifacts)
        for item in progress:
            if item.accepted and item.best_artifact_id is not None:
                selected[item.slot] = state.artifact_by_id(item.best_artifact_id)
        best_build = Build(
            artifacts=selected,
            base_stats=state.character.base_stats,
        )
        if all(item.main_value is not None for item in selected.values()):
            best_build = self.optimizer.evaluate(best_build, goal)
        summary = {
            "decision": decision.value,
            "reason": reason.value,
            "runs": runs,
            "resin_spent": spent,
        }
        recommendation = self.narrator.final(summary)
        trace.append(TraceEvent(event="session_finished", details=summary))
        return FarmSessionResult(
            decision=decision,
            reason=reason,
            runs=runs,
            resin_spent=spent,
            resin_remaining=adapter.resin_remaining,
            model_checkpoints=checkpoints,
            slot_progress=progress,
            collected_artifacts=collected,
            best_build=best_build,
            recommendation=recommendation,
            trace=trace,
        )
