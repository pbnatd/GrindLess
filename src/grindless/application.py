from __future__ import annotations

from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from .agent import GrindLessAgent
from .character_catalog import (
    CHARACTERS,
    CharacterDefinition,
    TeamIntent,
    TeamPlan,
    build_team_plan,
    character_goal,
)
from .enka import EnkaCharacterProfile
from .fixtures import mavuika_goal
from .good_import import GoodImportReport, import_good
from .llm import LLMBackend
from .models import (
    AccountState,
    Artifact,
    BaselineMode,
    BuildContext,
    CharacterProfile,
    FarmGoal,
    FarmPolicy,
    FarmSessionResult,
    InitialBuildAudit,
    Slot,
    SlotGoal,
    Stat,
)
from .optimizer import BruteForceBuildOptimizer
from .ports import Narrator
from .rotation_strategy import ValidatedRotation, validate_resolved_rotation
from .simulator import ArtifactDomainSimulator


class InventorySummary(BaseModel):
    artifacts: int
    five_star_artifacts: int
    level_zero_artifacts: int
    equipped_artifacts: int
    locked_artifacts: int
    sets: dict[str, int]


class SlotGoalView(BaseModel):
    slot: Slot
    allowed_sets: list[str]
    allowed_main_stats: list[Stat]
    main_stat_priorities: dict[Stat, int]
    substat_priorities: dict[Stat, float]
    min_useful_substats: int


class MavuikaInventoryAnalysis(BaseModel):
    preset: BuildContext
    policy: FarmPolicy
    import_report: GoodImportReport
    inventory: InventorySummary
    goals: list[SlotGoalView]
    audit: InitialBuildAudit


class CharacterInventoryAnalysis(BaseModel):
    character: CharacterDefinition
    profile: EnkaCharacterProfile
    team_plan: TeamPlan
    preset: BuildContext
    policy: FarmPolicy
    import_report: GoodImportReport
    inventory: InventorySummary
    goals: list[SlotGoalView]
    audit: InitialBuildAudit


class CharacterInventoryAnalysisRequest(BaseModel):
    inventory: dict[str, Any]
    team_intent: TeamIntent
    enka_collection_id: str


class MavuikaFarmSimulationRequest(BaseModel):
    inventory: dict[str, Any]
    policy: FarmPolicy = FarmPolicy.ECONOMY
    target_slots: list[Slot] = Field(min_length=1, max_length=5)
    resin_budget: Annotated[int, Field(ge=20, le=200, multiple_of=20)] = 200
    seed: Annotated[int, Field(ge=0, le=2_147_483_647)] = 386
    llm_backend: LLMBackend = LLMBackend.OFFLINE

    @model_validator(mode="after")
    def validate_unique_slots(self) -> MavuikaFarmSimulationRequest:
        if len(self.target_slots) != len(set(self.target_slots)):
            raise ValueError("target_slots must be unique")
        return self


class CharacterFarmSimulationRequest(MavuikaFarmSimulationRequest):
    team_intent: TeamIntent
    enka_collection_id: str
    artifact_goal: FarmGoal | None = None
    rotation_plan: ValidatedRotation | None = None


class SimulationArtifactView(BaseModel):
    artifact_id: str
    slot: Slot
    set_name: str
    main_stat: Stat
    substats: list[Stat]
    relevant: bool
    promising: bool
    baseline_eligible: bool
    matched_substats: list[Stat]
    content_score: float | None = None
    baseline_content_score: float | None = None


class SimulationRunView(BaseModel):
    run: int
    resin_spent_total: int
    resin_remaining: int
    analyzed: bool
    accepted_slots_after: list[Slot]
    artifacts: list[SimulationArtifactView]
    stop_here: bool


class MavuikaFarmSimulation(BaseModel):
    policy: FarmPolicy
    target_slots: list[Slot]
    resin_budget: int
    reward_cost: int
    seed: int
    baseline_artifact_ids: dict[Slot, str]
    checkpoint_strategy: str
    probability_notice: str
    enhancement_notice: str
    result: FarmSessionResult
    runs: list[SimulationRunView]


class CharacterFarmSimulation(MavuikaFarmSimulation):
    character: CharacterDefinition
    profile: EnkaCharacterProfile
    team_plan: TeamPlan
    artifact_goal_source: Literal["profile", "llm"]
    rotation_plan_source: Literal["none", "llm"]
    rotation_execution_status: Literal["not_executed"] = "not_executed"
    validated_rotation: ValidatedRotation | None = None


def describe_mavuika_preset(
    policy: FarmPolicy = FarmPolicy.ECONOMY,
) -> tuple[BuildContext, list[SlotGoalView]]:
    goal = mavuika_goal(policy)
    if goal.build_context is None:
        raise RuntimeError("the Mavuika preset has no build context")
    return goal.build_context, [_goal_view(target) for target in goal.targets]


def analyze_mavuika_inventory(
    payload: dict[str, Any],
    *,
    policy: FarmPolicy = FarmPolicy.ECONOMY,
    top_per_slot: int = 5,
) -> MavuikaInventoryAnalysis:
    if top_per_slot < 1 or top_per_slot > 20:
        raise ValueError("top_per_slot must be between 1 and 20")

    inventory = import_good(payload)
    if not inventory.artifacts:
        raise ValueError("GOOD contains no artifacts")

    goal = mavuika_goal(policy)
    if goal.build_context is None:
        raise RuntimeError("the Mavuika preset has no build context")
    audit = BruteForceBuildOptimizer().audit_initial_build(
        inventory.artifacts,
        goal,
        top_per_slot=top_per_slot,
    )
    set_counts = Counter(item.set_name for item in inventory.artifacts)

    return MavuikaInventoryAnalysis(
        preset=goal.build_context,
        policy=policy,
        import_report=inventory.report,
        inventory=InventorySummary(
            artifacts=len(inventory.artifacts),
            five_star_artifacts=sum(item.rarity == 5 for item in inventory.artifacts),
            level_zero_artifacts=sum(item.level == 0 for item in inventory.artifacts),
            equipped_artifacts=sum(
                item.equipped_by is not None for item in inventory.artifacts
            ),
            locked_artifacts=sum(item.locked for item in inventory.artifacts),
            sets=dict(sorted(set_counts.items())),
        ),
        goals=[_goal_view(target) for target in goal.targets],
        audit=audit,
    )


def describe_character_preset(
    key: str,
    policy: FarmPolicy = FarmPolicy.ECONOMY,
) -> tuple[CharacterDefinition, list[SlotGoalView]]:
    definition = CHARACTERS.get(key)
    if definition is None or not definition.full_target_support:
        raise ValueError(f"unsupported target character: {key}")
    goal = character_goal(key, policy)
    return definition, [_goal_view(target) for target in goal.targets]


def analyze_character_inventory(
    payload: dict[str, Any],
    *,
    team_intent: TeamIntent,
    profile: EnkaCharacterProfile,
    policy: FarmPolicy = FarmPolicy.ECONOMY,
    top_per_slot: int = 5,
) -> CharacterInventoryAnalysis:
    if profile.character_key != team_intent.target_key:
        raise ValueError("Enka profile does not match the selected target")
    if top_per_slot < 1 or top_per_slot > 20:
        raise ValueError("top_per_slot must be between 1 and 20")
    definition = CHARACTERS.get(team_intent.target_key)
    if definition is None or not definition.full_target_support:
        raise ValueError(f"unsupported target character: {team_intent.target_key}")
    inventory = import_good(payload)
    if not inventory.artifacts:
        raise ValueError("GOOD contains no artifacts")
    goal = character_goal(team_intent.target_key, policy)
    audit = BruteForceBuildOptimizer().audit_initial_build(
        inventory.artifacts,
        goal,
        top_per_slot=top_per_slot,
    )
    plan = build_team_plan(team_intent)
    set_counts = Counter(item.set_name for item in inventory.artifacts)
    preset = BuildContext(
        character=team_intent.target_key,
        constellation=profile.constellation,
        weapon=(f"weapon:{profile.weapon_id}" if profile.weapon_id else "unknown"),
        weapon_refinement=profile.weapon_refinement or 1,
        target_team=(
            plan.target_team
            if len(plan.target_team) == 4
            else [team_intent.target_key, "pending", "pending", "pending"]
        ),
        farming_team=(
            plan.domain_team
            if len(plan.domain_team) == 4
            else ["pending", "pending", "pending", "pending"]
        ),
    )
    return CharacterInventoryAnalysis(
        character=definition,
        profile=profile,
        team_plan=plan,
        preset=preset,
        policy=policy,
        import_report=inventory.report,
        inventory=InventorySummary(
            artifacts=len(inventory.artifacts),
            five_star_artifacts=sum(item.rarity == 5 for item in inventory.artifacts),
            level_zero_artifacts=sum(item.level == 0 for item in inventory.artifacts),
            equipped_artifacts=sum(item.equipped_by is not None for item in inventory.artifacts),
            locked_artifacts=sum(item.locked for item in inventory.artifacts),
            sets=dict(sorted(set_counts.items())),
        ),
        goals=[_goal_view(target) for target in goal.targets],
        audit=audit,
    )
def simulate_mavuika_farm(
    request: MavuikaFarmSimulationRequest,
    *,
    narrator: Narrator | None = None,
) -> MavuikaFarmSimulation:
    """Run the real decision loop against the seeded teaching simulator.

    Imported artifacts form a frozen provisional baseline. Synthetic drops are
    produced only by the FarmAdapter; the agent and optimizer are the same
    components a future game adapter will call.
    """

    analysis = analyze_mavuika_inventory(
        request.inventory,
        policy=request.policy,
        top_per_slot=5,
    )
    imported = import_good(request.inventory)
    base_goal = mavuika_goal(request.policy)
    target_by_slot = {target.slot: target for target in base_goal.targets}
    selected_targets = [target_by_slot[slot] for slot in request.target_slots]
    goal = base_goal.model_copy(
        update={
            "targets": selected_targets,
            "resin_budget": request.resin_budget,
            "baseline_mode": (
                BaselineMode.EQUIPPED
                if analysis.audit.starter_build_available
                else BaselineMode.EMPTY
            ),
        }
    )
    state = AccountState(
        character=CharacterProfile(
            name=goal.character,
            equipped_artifact_ids=dict(analysis.audit.selected_artifact_ids),
        ),
        artifacts=imported.artifacts,
    )
    simulator = ArtifactDomainSimulator(
        seed=request.seed,
        resin=request.resin_budget,
        domain_sets=("ObsidianCodex", "ScrollOfTheHeroOfCinderCity"),
    )
    result = GrindLessAgent(narrator=narrator).run(
        state=state,
        goal=goal,
        adapter=simulator,
    )

    return MavuikaFarmSimulation(
        policy=request.policy,
        target_slots=request.target_slots,
        resin_budget=request.resin_budget,
        reward_cost=goal.reward_cost,
        seed=request.seed,
        baseline_artifact_ids=dict(analysis.audit.selected_artifact_ids),
        checkpoint_strategy=(
            "after_each_reward"
            if request.policy is FarmPolicy.ECONOMY
            else "after_final_reward"
        ),
        probability_notice=(
            "Teaching simulation: artifact probabilities are configurable "
            "approximations, not official Genshin Impact drop rates."
        ),
        enhancement_notice=(
            "Artifact enhancement is disabled: no +0 to +20 rolls are simulated."
        ),
        result=result,
        runs=_simulation_run_views(
            result,
            policy=request.policy,
            resin_budget=request.resin_budget,
            reward_cost=goal.reward_cost,
        ),
    )


def simulate_character_farm(
    request: CharacterFarmSimulationRequest,
    *,
    profile: EnkaCharacterProfile,
    narrator: Narrator | None = None,
) -> CharacterFarmSimulation:
    analysis = analyze_character_inventory(
        request.inventory,
        team_intent=request.team_intent,
        profile=profile,
        policy=request.policy,
        top_per_slot=5,
    )
    imported = import_good(request.inventory)
    if request.rotation_plan is not None:
        validate_resolved_rotation(request.rotation_plan, analysis.team_plan)
    base_goal = request.artifact_goal or character_goal(
        request.team_intent.target_key, request.policy
    )
    if request.artifact_goal is not None:
        from .artifact_strategy import validate_resolved_artifact_goal

        validate_resolved_artifact_goal(
            base_goal,
            target_key=request.team_intent.target_key,
        )
        base_goal = base_goal.model_copy(update={"policy": request.policy})
    audit = BruteForceBuildOptimizer().audit_initial_build(
        imported.artifacts,
        base_goal,
        top_per_slot=5,
    )
    target_by_slot = {target.slot: target for target in base_goal.targets}
    goal = base_goal.model_copy(
        update={
            "targets": [target_by_slot[slot] for slot in request.target_slots],
            "resin_budget": request.resin_budget,
            "baseline_mode": (
                BaselineMode.EQUIPPED
                if audit.starter_build_available
                else BaselineMode.EMPTY
            ),
        }
    )
    state = AccountState(
        character=CharacterProfile(
            name=goal.character,
            equipped_artifact_ids=dict(audit.selected_artifact_ids),
        ),
        artifacts=imported.artifacts,
    )
    definition = analysis.character
    required_sets = [
        item.set_name for item in goal.constraints.set_requirements
    ]
    if len(required_sets) == 1:
        fallback = next(
            (
                item
                for item in (definition.primary_set, definition.secondary_set)
                if item != required_sets[0]
            ),
            required_sets[0],
        )
        simulated_sets = (required_sets[0], fallback)
    elif len(required_sets) == 2:
        simulated_sets = (required_sets[0], required_sets[1])
    else:
        simulated_sets = (definition.primary_set, definition.secondary_set)
    simulator = ArtifactDomainSimulator(
        seed=request.seed,
        resin=request.resin_budget,
        domain_sets=simulated_sets,
    )
    result = GrindLessAgent(narrator=narrator).run(
        state=state,
        goal=goal,
        adapter=simulator,
    )
    return CharacterFarmSimulation(
        character=definition,
        profile=profile,
        team_plan=analysis.team_plan,
        artifact_goal_source=("llm" if request.artifact_goal is not None else "profile"),
        rotation_plan_source=("llm" if request.rotation_plan is not None else "none"),
        validated_rotation=request.rotation_plan,
        policy=request.policy,
        target_slots=request.target_slots,
        resin_budget=request.resin_budget,
        reward_cost=goal.reward_cost,
        seed=request.seed,
        baseline_artifact_ids=dict(audit.selected_artifact_ids),
        checkpoint_strategy=(
            "after_each_reward"
            if request.policy is FarmPolicy.ECONOMY
            else "after_final_reward"
        ),
        probability_notice=(
            "Teaching simulation: artifact probabilities are configurable "
            "approximations, not official Genshin Impact drop rates."
        ),
        enhancement_notice=(
            "Artifact enhancement is disabled: no +0 to +20 rolls are simulated."
        ),
        result=result,
        runs=_simulation_run_views(
            result,
            policy=request.policy,
            resin_budget=request.resin_budget,
            reward_cost=goal.reward_cost,
        ),
    )


def _goal_view(target: SlotGoal) -> SlotGoalView:
    return SlotGoalView(
        slot=target.slot,
        allowed_sets=sorted(target.allowed_sets),
        allowed_main_stats=sorted(target.allowed_main_stats, key=str),
        main_stat_priorities=dict(
            sorted(target.main_stat_priorities.items(), key=lambda item: str(item[0]))
        ),
        substat_priorities=dict(
            sorted(target.substat_priorities.items(), key=lambda item: str(item[0]))
        ),
        min_useful_substats=target.min_useful_substats,
    )


def _simulation_run_views(
    result: FarmSessionResult,
    *,
    policy: FarmPolicy,
    resin_budget: int,
    reward_cost: int,
) -> list[SimulationRunView]:
    artifacts_by_id: dict[str, Artifact] = {
        item.id: item for item in result.collected_artifacts
    }
    evaluations: dict[tuple[int, str], dict[str, object]] = {}
    ids_by_run: dict[int, list[str]] = {}
    accepted_by_run: dict[int, list[Slot]] = {}

    for event in result.trace:
        details = event.details
        if event.event == "artifact_evaluated":
            run = int(details["run"])
            artifact_id = str(details["artifact_id"])
            evaluations[(run, artifact_id)] = details
            ids_by_run.setdefault(run, []).append(artifact_id)
        elif event.event == "checkpoint":
            run = int(details["run"])
            accepted_by_run[run] = [
                Slot(str(slot)) for slot in details.get("accepted_slots", [])
            ]

    final_accepted = [item.slot for item in result.slot_progress if item.accepted]
    views: list[SimulationRunView] = []
    for run in range(1, result.runs + 1):
        artifact_views: list[SimulationArtifactView] = []
        for artifact_id in ids_by_run.get(run, []):
            artifact = artifacts_by_id[artifact_id]
            details = evaluations[(run, artifact_id)]
            artifact_views.append(
                SimulationArtifactView(
                    artifact_id=artifact.id,
                    slot=artifact.slot,
                    set_name=artifact.set_name,
                    main_stat=artifact.main_stat,
                    substats=[item.stat for item in artifact.substats],
                    relevant=bool(details["relevant"]),
                    promising=bool(details["promising"]),
                    baseline_eligible=bool(details.get("baseline_eligible", True)),
                    matched_substats=[
                        Stat(str(item)) for item in details.get("matched_substats", [])
                    ],
                    content_score=(
                        float(details["content_score"])
                        if "content_score" in details
                        else None
                    ),
                    baseline_content_score=(
                        float(details["baseline_content_score"])
                        if "baseline_content_score" in details
                        else None
                    ),
                )
            )

        analyzed = policy is FarmPolicy.ECONOMY or run == result.runs
        accepted = accepted_by_run.get(run, [])
        if policy is FarmPolicy.SPEND_ALL and run == result.runs:
            accepted = final_accepted
        views.append(
            SimulationRunView(
                run=run,
                resin_spent_total=run * reward_cost,
                resin_remaining=max(0, resin_budget - run * reward_cost),
                analyzed=analyzed,
                accepted_slots_after=accepted,
                artifacts=artifact_views,
                stop_here=run == result.runs,
            )
        )
    return views
