from __future__ import annotations

from typing import Protocol

from .models import (
    AccountState,
    Artifact,
    Build,
    EnhancementResult,
    FarmGoal,
    RewardBatch,
    SlotProgress,
)


class FarmAdapter(Protocol):
    """Boundary implemented by the simulator now and the game adapter later."""

    @property
    def resin_remaining(self) -> int: ...

    def claim_reward(self, cost: int) -> RewardBatch: ...

    def enhance_artifact(self, artifact: Artifact, target_level: int = 20) -> EnhancementResult: ...


class BuildOptimizer(Protocol):
    def evaluate(self, build: Build, goal: FarmGoal) -> Build: ...

    def optimize(self, state: AccountState, goal: FarmGoal) -> Build: ...

    def assess_targets(
        self, state: AccountState, baseline: Build, goal: FarmGoal
    ) -> list[SlotProgress]: ...


class ExpectedGainEstimator(Protocol):
    def gain_per_resin(self, state: AccountState, goal: FarmGoal) -> float | None: ...


class Narrator(Protocol):
    """LLM boundary. A template implementation keeps the MVP offline."""

    def checkpoint(self, run_number: int, progress: list[SlotProgress]) -> str: ...

    def final(self, result_summary: dict[str, object]) -> str: ...
