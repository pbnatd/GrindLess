from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class Slot(StrEnum):
    FLOWER = "flower"
    PLUME = "plume"
    SANDS = "sands"
    GOBLET = "goblet"
    CIRCLET = "circlet"


class Stat(StrEnum):
    HP_FLAT = "hp_flat"
    ATK_FLAT = "atk_flat"
    DEF_FLAT = "def_flat"
    HP_PCT = "hp_pct"
    ATK_PCT = "atk_pct"
    DEF_PCT = "def_pct"
    ELEMENTAL_MASTERY = "elemental_mastery"
    ENERGY_RECHARGE = "energy_recharge"
    CRIT_RATE = "crit_rate"
    CRIT_DMG = "crit_dmg"
    PYRO_DMG = "pyro_dmg"
    PHYSICAL_DMG = "physical_dmg"
    ANEMO_DMG = "anemo_dmg"
    GEO_DMG = "geo_dmg"
    ELECTRO_DMG = "electro_dmg"
    HYDRO_DMG = "hydro_dmg"
    CRYO_DMG = "cryo_dmg"
    DENDRO_DMG = "dendro_dmg"
    HEALING_BONUS = "healing_bonus"


class FarmPolicy(StrEnum):
    SPEND_ALL = "spend_all"
    ECONOMY = "economy"


class BaselineMode(StrEnum):
    EQUIPPED = "equipped"
    EMPTY = "empty"


class Decision(StrEnum):
    REPEAT = "repeat"
    STOP = "stop"
    CHANGE_GOAL = "change_goal"
    SAFE_STOP = "safe_stop"


class StopReason(StrEnum):
    FULL_BUDGET_SPENT = "full_budget_spent"
    ALL_SLOT_GOALS_MET = "all_slot_goals_met"
    RESIN_EXHAUSTED = "resin_exhausted"
    GUARANTEED_UPGRADE_IS_BETTER = "guaranteed_upgrade_is_better"
    UNKNOWN_STATE = "unknown_state"
    REWARD_NOT_CONFIRMED = "reward_not_confirmed"


class Substat(BaseModel):
    stat: Stat
    value: Annotated[float, Field(gt=0)]
    initial_value: float | None = None


class Artifact(BaseModel):
    id: str
    set_name: str
    slot: Slot
    rarity: Annotated[int, Field(ge=1, le=5)] = 5
    level: Annotated[int, Field(ge=0, le=20)] = 0
    main_stat: Stat
    # GOOD does not carry the derived numeric main-stat value. It is optional
    # because the default content-only evaluator does not need it.
    main_value: Annotated[float, Field(gt=0)] | None = None
    substats: list[Substat] = Field(default_factory=list, max_length=4)
    # GOOD v3 may expose a known-but-not-yet-activated substat separately.
    # It participates in content-only comparison, but not numeric build totals.
    unactivated_substats: list[Substat] = Field(default_factory=list, max_length=4)
    total_rolls: Annotated[int, Field(ge=0, le=9)] | None = None
    astral_mark: bool | None = None
    elixir_crafted: bool | None = None
    equipped_by: str | None = None
    locked: bool = False
    source: str = "simulator"
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0
    source_index: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def validate_stats(self) -> Artifact:
        names = [
            item.stat
            for item in [*self.substats, *self.unactivated_substats]
        ]
        if len(names) != len(set(names)):
            raise ValueError("artifact active and unactivated substats must be unique")
        if len(names) > 4:
            raise ValueError("artifact cannot expose more than four substats")
        if self.main_stat in names:
            raise ValueError("main stat cannot also be a substat")
        return self

    @property
    def known_substats(self) -> list[Substat]:
        """All observed substat types, including GOOD v3's inactive line."""

        return [*self.substats, *self.unactivated_substats]

    def stat_total(self, stat: Stat) -> float:
        total = (self.main_value or 0.0) if self.main_stat == stat else 0.0
        return total + sum(item.value for item in self.substats if item.stat == stat)


class Build(BaseModel):
    artifacts: dict[Slot, Artifact]
    base_stats: dict[Stat, float] = Field(default_factory=dict)
    score: float = 0.0
    stat_totals: dict[Stat, float] = Field(default_factory=dict)
    constraints_met: bool = False

    @model_validator(mode="after")
    def validate_slots(self) -> Build:
        for slot, artifact in self.artifacts.items():
            if artifact.slot != slot:
                raise ValueError(f"artifact {artifact.id} does not belong to {slot}")
        return self


class CharacterTalents(BaseModel):
    auto: Annotated[int, Field(ge=1, le=15)]
    skill: Annotated[int, Field(ge=1, le=15)]
    burst: Annotated[int, Field(ge=1, le=15)]


class WeaponProfile(BaseModel):
    id: str
    key: str
    level: Annotated[int, Field(ge=1, le=90)]
    ascension: Annotated[int, Field(ge=0, le=6)]
    refinement: Annotated[int, Field(ge=1, le=5)]
    equipped_by: str | None = None
    locked: bool = False
    source: str = "good"
    source_index: Annotated[int, Field(ge=1)] | None = None


class CharacterProfile(BaseModel):
    name: str
    level: Annotated[int, Field(ge=1, le=100)] | None = None
    constellation: Annotated[int, Field(ge=0, le=6)] | None = None
    ascension: Annotated[int, Field(ge=0, le=6)] | None = None
    talents: CharacterTalents | None = None
    equipped_weapon_id: str | None = None
    base_stats: dict[Stat, float] = Field(default_factory=dict)
    equipped_artifact_ids: dict[Slot, str] = Field(default_factory=dict)


class BuildContext(BaseModel):
    character: str
    constellation: Annotated[int, Field(ge=0, le=6)]
    weapon: str
    weapon_refinement: Annotated[int, Field(ge=1, le=5)]
    target_team: list[str] = Field(min_length=4, max_length=4)
    farming_team: list[str] = Field(min_length=4, max_length=4)


class AccountState(BaseModel):
    character: CharacterProfile
    artifacts: list[Artifact]
    protected_characters: set[str] = Field(default_factory=set)

    def artifact_by_id(self, artifact_id: str) -> Artifact:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        raise KeyError(f"unknown artifact: {artifact_id}")

    def equipped_build(self) -> Build:
        return Build(
            artifacts={
                slot: self.artifact_by_id(artifact_id)
                for slot, artifact_id in self.character.equipped_artifact_ids.items()
            },
            base_stats=self.character.base_stats,
        )


class ArtifactSetRequirement(BaseModel):
    set_name: str = Field(min_length=1, max_length=100)
    pieces: Literal[2, 4]


class BuildConstraints(BaseModel):
    stat_weights: dict[Stat, float]
    minimum_stats: dict[Stat, float] = Field(default_factory=dict)
    set_requirements: list[ArtifactSetRequirement] = Field(
        default_factory=list, max_length=2
    )

    @model_validator(mode="after")
    def validate_set_requirements(self) -> BuildConstraints:
        names = [item.set_name for item in self.set_requirements]
        if len(names) != len(set(names)):
            raise ValueError("set requirements must use distinct artifact sets")
        pieces = sorted(item.pieces for item in self.set_requirements)
        if pieces not in ([], [4], [2, 2]):
            raise ValueError("set requirements must be one 4pc set or two 2pc sets")
        return self


class SlotGoal(BaseModel):
    slot: Slot
    allowed_main_stats: set[Stat] = Field(default_factory=set)
    allowed_sets: set[str] = Field(default_factory=set)
    # Optional relative ordering among allowed main stats. It does not replace
    # the allowed set and never uses rolled artifact values.
    main_stat_priorities: dict[Stat, Annotated[int, Field(ge=1)]] = Field(
        default_factory=dict
    )
    # These are build priorities, never the rolled values of an artifact.
    substat_priorities: dict[Stat, Annotated[float, Field(gt=0)]] = Field(
        default_factory=dict
    )
    min_useful_substats: Annotated[int, Field(ge=0, le=4)] = 2
    min_content_score_gain: Annotated[float, Field(gt=0)] = 1.0
    # Used only after explicit enhancement authorization.
    min_gain: Annotated[float, Field(ge=0)] = 0.01

    @model_validator(mode="after")
    def validate_main_stat_priorities(self) -> SlotGoal:
        if self.allowed_main_stats and not set(self.main_stat_priorities).issubset(
            self.allowed_main_stats
        ):
            raise ValueError("main_stat_priorities must be allowed main stats")
        return self


class EnhancementAuthorization(BaseModel):
    """Explicit, bounded permission to spend artifact-enhancement materials."""

    enabled: bool = False
    max_artifacts: Annotated[int, Field(ge=0, le=50)] = 0
    target_level: Literal[4, 8, 12, 16, 20] = 20

    @model_validator(mode="after")
    def validate_budget(self) -> EnhancementAuthorization:
        if self.enabled and self.max_artifacts == 0:
            raise ValueError("enabled enhancement requires max_artifacts > 0")
        if not self.enabled and self.max_artifacts != 0:
            raise ValueError("disabled enhancement must have max_artifacts = 0")
        return self


class GuaranteedUpgrade(BaseModel):
    name: str
    expected_gain: Annotated[float, Field(gt=0)]
    resin_cost: Annotated[int, Field(gt=0)]

    @property
    def gain_per_resin(self) -> float:
        return self.expected_gain / self.resin_cost


class FarmGoal(BaseModel):
    character: str
    targets: list[SlotGoal] = Field(min_length=1)
    policy: FarmPolicy
    constraints: BuildConstraints
    resin_budget: Annotated[int, Field(ge=0, le=200)] = 200
    reward_cost: Annotated[int, Field(gt=0)] = 20
    enhancement: EnhancementAuthorization = Field(
        default_factory=EnhancementAuthorization
    )
    configured_artifact_gain_per_resin: Annotated[float, Field(ge=0)] | None = None
    alternative_upgrade: GuaranteedUpgrade | None = None
    baseline_mode: BaselineMode = BaselineMode.EQUIPPED
    build_context: BuildContext | None = None

    @model_validator(mode="after")
    def validate_targets(self) -> FarmGoal:
        slots = [target.slot for target in self.targets]
        if len(slots) != len(set(slots)):
            raise ValueError("target slots must be unique")
        return self


class RewardBatch(BaseModel):
    run_number: int
    artifacts: list[Artifact]
    resin_spent: int
    reward_confirmed: bool = True
    observation_confidence: Annotated[float, Field(ge=0, le=1)] = 1.0


class EnhancementEvent(BaseModel):
    artifact_id: str
    from_level: int
    to_level: int
    changed_stat: Stat
    added_new_substat: bool


class EnhancementResult(BaseModel):
    artifact: Artifact
    events: list[EnhancementEvent]


class SlotProgress(BaseModel):
    slot: Slot
    # Missing IDs are first-class evidence: the user may start farming before
    # any suitable artifact exists for this slot.
    baseline_artifact_id: str | None = None
    best_artifact_id: str | None = None
    evaluation_mode: Literal["content_only", "enhanced_values"]
    baseline_content_score: float
    candidate_content_score: float
    content_score_gain: float
    matched_substats: list[Stat] = Field(default_factory=list)
    relative_gain: float | None = None
    accepted: bool
    reason: str


class ArtifactCandidate(BaseModel):
    artifact_id: str
    source_index: int | None
    slot: Slot
    set_name: str
    main_stat: Stat
    main_stat_priority: int
    substats: list[Stat]
    matched_substats: list[Stat]
    content_score: float
    useful_substat_count: int
    observed_substat_count: int
    closes_goal: bool


class InitialBuildAudit(BaseModel):
    character: str
    baseline_mode: Literal["empty"] = "empty"
    candidates: dict[Slot, list[ArtifactCandidate]]
    selected_artifact_ids: dict[Slot, str]
    selected_set_counts: dict[str, int] = Field(default_factory=dict)
    set_composition_met: bool = False
    off_piece_artifact_id: str | None = None
    pending_slots: list[Slot]
    starter_build_available: bool


class TraceEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event: str
    details: dict[str, object] = Field(default_factory=dict)


class FarmSessionResult(BaseModel):
    decision: Decision
    reason: StopReason
    runs: int
    resin_spent: int
    resin_remaining: int
    model_checkpoints: int
    slot_progress: list[SlotProgress]
    collected_artifacts: list[Artifact]
    best_build: Build
    recommendation: str
    trace: list[TraceEvent]
