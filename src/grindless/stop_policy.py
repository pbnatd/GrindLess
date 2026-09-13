from __future__ import annotations

from .models import AccountState, FarmGoal, FarmPolicy, SlotProgress


class ConfiguredExpectedGainEstimator:
    """Initial estimator with an explicit, inspectable configuration value.

    A calibrated Monte Carlo estimator can replace it through the same method.
    The estimate decreases as target slots are completed.
    """

    def gain_per_resin(
        self,
        state: AccountState,
        goal: FarmGoal,
        progress: list[SlotProgress] | None = None,
    ) -> float | None:
        del state
        if goal.configured_artifact_gain_per_resin is None:
            return None
        if not progress:
            return goal.configured_artifact_gain_per_resin
        remaining = sum(not item.accepted for item in progress)
        return goal.configured_artifact_gain_per_resin * remaining / len(progress)

    def should_change_goal(
        self,
        state: AccountState,
        goal: FarmGoal,
        progress: list[SlotProgress] | None = None,
    ) -> bool:
        if goal.policy != FarmPolicy.ECONOMY or goal.alternative_upgrade is None:
            return False
        artifact_gain = self.gain_per_resin(state, goal, progress)
        return artifact_gain is not None and artifact_gain < goal.alternative_upgrade.gain_per_resin
