from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .artifact_strategy import validate_resolved_artifact_goal
from .character_catalog import CHARACTERS, TeamIntent, TeamPlan, build_team_plan
from .enka import EnkaCharacterProfile
from .llm import (
    AuditedLLM,
    LLMBackend,
    LLMRequest,
    NarrationReport,
    ReasoningEffort,
)
from .models import ArtifactSetRequirement, FarmGoal, Slot, Stat
from .prompt_style import RUSSIAN_UI_COPY_STYLE
from .structured_output import StructuredOutputError, complete_json_with_truncation_retry

RotationAction = Literal[
    "skill",
    "burst",
    "normal_attack",
    "charged_attack",
    "dodge",
]
BurstRecovery = Literal[
    "use_skill_then_retry",
    "skip_step",
    "restart_rotation",
    "safe_stop",
]


class RotationStrategyRequest(BaseModel):
    team_intent: TeamIntent
    enka_collection_id: str = Field(min_length=16, max_length=256)
    llm_backend: LLMBackend
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    artifact_goal: FarmGoal | None = None
    preferences: str = Field(default="", max_length=2_000)


class RotationMemberEvidence(BaseModel):
    character_key: str
    name_ru: str
    element: str
    role: str
    role_evidence: Literal["curated", "identity_only"]
    constellation: int
    skill_levels: dict[str, int]


class RotationArtifactGoalEvidence(BaseModel):
    set_requirements: list[ArtifactSetRequirement]
    main_stats: dict[Slot, list[Stat]]
    substat_priority_order: list[Stat]
    energy_recharge_rank: int | None


class RotationEvidence(BaseModel):
    domain_team: list[str]
    members: list[RotationMemberEvidence]
    artifact_goal: RotationArtifactGoalEvidence | None
    allowed_actions: list[RotationAction]
    preferences: str
    knowledge_limitations: list[str]
    privacy_notice: str = (
        "OpenAI receives the confirmed domain team, selected Enka combat fields, the user "
        "comment and the resolved artifact-goal summary. Web search sends search queries. "
        "UID, raw GOOD, artifacts and video are not sent."
    )


class RotationStepDraft(BaseModel):
    character_key: str
    action: RotationAction
    repetitions: int = Field(default=1, ge=1, le=5)
    purpose_ru: str = Field(min_length=15, max_length=500)


class BurstFallbackDraft(BaseModel):
    at_step: int = Field(ge=1, le=24)
    response: BurstRecovery
    rationale_ru: str = Field(min_length=15, max_length=500)


class RotationDraft(BaseModel):
    domain_team: list[str] = Field(min_length=4, max_length=4)
    opening_ru: str = Field(min_length=20, max_length=1_000)
    steps: list[RotationStepDraft] = Field(min_length=4, max_length=24)
    burst_fallbacks: list[BurstFallbackDraft] = Field(default_factory=list, max_length=12)
    repeat_from_step: int = Field(ge=1, le=24)
    stop_conditions_ru: list[str] = Field(min_length=1, max_length=6)
    preference_handling_ru: str = Field(default="", max_length=1_000)
    assumptions_ru: list[str] = Field(default_factory=list, max_length=8)
    rationale_ru: str = Field(min_length=20, max_length=1_500)
    confidence: Literal["high", "medium", "low"]


class CompiledRotationState(BaseModel):
    state_id: str
    character_key: str
    action: RotationAction
    repetitions: int
    on_success: str
    on_failure: Literal["safe_stop"] = "safe_stop"
    on_burst_unavailable: str | None = None
    source_step: int
    recovery: bool = False
    purpose_ru: str = Field(min_length=15, max_length=500)
    fallback_rationale_ru: str | None = Field(default=None, min_length=15, max_length=500)


class ValidatedRotation(BaseModel):
    domain_team: list[str]
    opening_ru: str = Field(min_length=20, max_length=1_000)
    rationale_ru: str = Field(min_length=20, max_length=1_500)
    stop_conditions_ru: list[str] = Field(min_length=1, max_length=6)
    assumptions_ru: list[str] = Field(default_factory=list, max_length=8)
    states: list[CompiledRotationState]
    entry_state: str
    repeat_state: str
    terminal_states: list[Literal["rotation_complete", "safe_stop"]]
    validation_level: Literal["structural_only"] = "structural_only"
    input_authority: Literal["none"] = "none"
    plan_fingerprint: str


class RotationValidation(BaseModel):
    passed: Literal[True] = True
    checks: list[str]
    knowledge_coverage: Literal[
        "curated", "partial", "identity_only", "web_researched"
    ]
    timing_status: Literal["unverified", "web_researched"] = "unverified"
    energy_status: Literal["unverified", "web_researched"] = "unverified"
    execution_status: Literal["blocked"] = "blocked"


class RotationStrategyResult(BaseModel):
    decision_owner: Literal["llm"] = "llm"
    execution_status: Literal["shadow_only"] = "shadow_only"
    draft: RotationDraft
    validated_rotation: ValidatedRotation
    validation: RotationValidation
    evidence: RotationEvidence
    llm_audit: NarrationReport


RotationOutputError = StructuredOutputError


class RotationEvidenceTool:
    """Project confirmed team state into bounded rotation-planning evidence."""

    @staticmethod
    def execute(
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        artifact_goal: FarmGoal | None,
        preferences: str,
    ) -> tuple[RotationEvidence, TeamPlan]:
        plan = build_team_plan(intent)
        if plan.target_team_status != "confirmed" or plan.domain_team_status == "pending_optimizer":
            raise ValueError(
                "rotation planning requires confirmed teams; build the team strategy first"
            )
        if len(plan.domain_team) != 4 or len(set(plan.domain_team)) != 4:
            raise ValueError("rotation planning requires four unique domain-team members")

        by_key = {profile.character_key: profile for profile in profiles}
        missing = sorted(set(plan.domain_team) - set(by_key))
        if missing:
            raise ValueError(
                "Enka collection does not confirm domain-team members: "
                + ", ".join(missing)
            )

        artifact_evidence = None
        if artifact_goal is not None:
            validate_resolved_artifact_goal(artifact_goal, target_key=intent.target_key)
            priorities = sorted(
                artifact_goal.constraints.stat_weights,
                key=lambda stat: (-artifact_goal.constraints.stat_weights[stat], str(stat)),
            )
            energy_rank = (
                priorities.index(Stat.ENERGY_RECHARGE) + 1
                if Stat.ENERGY_RECHARGE in priorities
                else None
            )
            artifact_evidence = RotationArtifactGoalEvidence(
                set_requirements=artifact_goal.constraints.set_requirements,
                main_stats={
                    target.slot: sorted(target.allowed_main_stats, key=str)
                    for target in artifact_goal.targets
                },
                substat_priority_order=priorities,
                energy_recharge_rank=energy_rank,
            )

        members = []
        identity_only = []
        for key in plan.domain_team:
            definition = CHARACTERS[key]
            profile = by_key[key]
            curated = definition.role != "team candidate"
            if not curated:
                identity_only.append(key)
            members.append(
                RotationMemberEvidence(
                    character_key=key,
                    name_ru=definition.name_ru,
                    element=definition.element,
                    role=definition.role,
                    role_evidence="curated" if curated else "identity_only",
                    constellation=profile.constellation,
                    skill_levels=profile.skill_levels,
                )
            )

        limitations = [
            "Откаты навыков, стоимость ульт и генерацию частиц нужно сверить по свежим источникам.",
            "Длительность анимаций, попадания и состояние врагов пока не отслеживаются.",
            "Ротация остаётся планом и не включает управление клавиатурой или мышью.",
        ]
        if identity_only:
            limitations.append(
                "В локальной базе пока нет подробного описания роли для: "
                + ", ".join(identity_only)
                + "."
            )
        if artifact_goal is None:
            limitations.append(
                "Отдельный план артефактов не выбран, поэтому требования к энергии нужно уточнить."
            )
        return RotationEvidence(
            domain_team=plan.domain_team,
            members=members,
            artifact_goal=artifact_evidence,
            allowed_actions=[
                "skill",
                "burst",
                "normal_attack",
                "charged_attack",
                "dodge",
            ],
            preferences=preferences.strip(),
            knowledge_limitations=limitations,
        ), plan


class RotationValidator:
    """Compile a model-owned semantic rotation without granting input authority."""

    @staticmethod
    def execute(
        draft: RotationDraft,
        evidence: RotationEvidence,
        *,
        web_research_used: bool = False,
    ) -> tuple[RotationDraft, ValidatedRotation, RotationValidation]:
        if len(set(draft.domain_team)) != 4 or set(draft.domain_team) != set(
            evidence.domain_team
        ):
            raise ValueError("model changed the confirmed domain team")
        if draft.repeat_from_step > len(draft.steps):
            raise ValueError("repeat_from_step points outside the rotation")
        if evidence.preferences and len(draft.preference_handling_ru.strip()) < 10:
            raise ValueError(
                "model did not explain how the user comment affected the rotation"
            )

        team = set(evidence.domain_team)
        seen = set()
        previous: RotationStepDraft | None = None
        burst_steps = set()
        for index, step in enumerate(draft.steps, start=1):
            if step.character_key not in team:
                raise ValueError(f"rotation step {index} uses a character outside the team")
            if step.action not in evidence.allowed_actions:
                raise ValueError(f"rotation step {index} uses an action outside the allowlist")
            if previous is not None and (
                step.character_key == previous.character_key
                and step.action == previous.action
            ):
                raise ValueError(
                    f"rotation steps {index - 1} and {index} duplicate an action; "
                    "use repetitions instead"
                )
            seen.add(step.character_key)
            if step.action == "burst":
                burst_steps.add(index)
            previous = step
        if seen != team:
            raise ValueError(
                "rotation does not use every domain-team member: "
                + ", ".join(sorted(team - seen))
            )

        fallback_by_step: dict[int, BurstFallbackDraft] = {}
        for fallback in draft.burst_fallbacks:
            if fallback.at_step in fallback_by_step:
                raise ValueError("rotation repeats a burst fallback for one step")
            if fallback.at_step not in burst_steps:
                raise ValueError("burst fallback points to a non-burst step")
            fallback_by_step[fallback.at_step] = fallback
        if set(fallback_by_step) != burst_steps:
            missing = sorted(burst_steps - set(fallback_by_step))
            raise ValueError(
                "every burst needs an explicit unavailable fallback; missing steps: "
                + ", ".join(map(str, missing))
            )

        states: list[CompiledRotationState] = []
        repeat_state = _step_id(draft.repeat_from_step)
        for index, step in enumerate(draft.steps, start=1):
            next_state = (
                _step_id(index + 1)
                if index < len(draft.steps)
                else "rotation_complete"
            )
            on_burst_unavailable = None
            fallback = fallback_by_step.get(index)
            if fallback is not None:
                if fallback.response == "use_skill_then_retry":
                    on_burst_unavailable = f"recovery_{index:02d}_skill"
                elif fallback.response == "skip_step":
                    on_burst_unavailable = next_state
                elif fallback.response == "restart_rotation":
                    on_burst_unavailable = repeat_state
                else:
                    on_burst_unavailable = "safe_stop"
            states.append(
                CompiledRotationState(
                    state_id=_step_id(index),
                    character_key=step.character_key,
                    action=step.action,
                    repetitions=step.repetitions,
                    on_success=next_state,
                    on_burst_unavailable=on_burst_unavailable,
                    source_step=index,
                    purpose_ru=step.purpose_ru,
                    fallback_rationale_ru=(fallback.rationale_ru if fallback else None),
                )
            )
            if fallback is not None and fallback.response == "use_skill_then_retry":
                states.append(
                    CompiledRotationState(
                        state_id=f"recovery_{index:02d}_skill",
                        character_key=step.character_key,
                        action="skill",
                        repetitions=1,
                        on_success=_step_id(index),
                        source_step=index,
                        recovery=True,
                        purpose_ru=(
                            "Восстановить взрыв стихии навыком и повторить исходный шаг."
                        ),
                        fallback_rationale_ru=fallback.rationale_ru,
                    )
                )

        local_coverage = _coverage(evidence.members)
        coverage = "web_researched" if web_research_used else local_coverage
        assumptions = list(draft.assumptions_ru)
        confidence = draft.confidence
        if local_coverage != "curated" and not web_research_used:
            assumptions.append(
                "Для части персонажей в локальной базе пока нет полного описания роли."
            )
            confidence = "low"
        elif confidence == "high" and not web_research_used:
            confidence = "medium"
            assumptions.append(
                "Перед использованием ротации нужно проверить откаты навыков, энергию и тайминги."
            )
        normalized = draft.model_copy(
            update={
                "domain_team": evidence.domain_team,
                "assumptions_ru": list(dict.fromkeys(assumptions)),
                "confidence": confidence,
            }
        )
        rotation = ValidatedRotation(
            domain_team=evidence.domain_team,
            opening_ru=normalized.opening_ru,
            rationale_ru=normalized.rationale_ru,
            stop_conditions_ru=normalized.stop_conditions_ru,
            assumptions_ru=normalized.assumptions_ru,
            states=states,
            entry_state="step_01",
            repeat_state=repeat_state,
            terminal_states=["rotation_complete", "safe_stop"],
            plan_fingerprint="pending",
        )
        rotation = rotation.model_copy(
            update={"plan_fingerprint": _rotation_fingerprint(rotation)}
        )
        return normalized, rotation, RotationValidation(
            checks=[
                "состав команды домена не изменён",
                "в ротации используются только поддерживаемые действия",
                "в ротации участвуют все четыре персонажа",
                "для каждой ульты предусмотрен запасной вариант",
                "неопределённое действие останавливает сессию",
                "план не содержит команд клавиатуры или мыши",
            ],
            knowledge_coverage=coverage,
            timing_status="web_researched" if web_research_used else "unverified",
            energy_status="web_researched" if web_research_used else "unverified",
        )


class RotationPlanner:
    def __init__(self, llm: AuditedLLM) -> None:
        self.llm = llm

    def plan(
        self,
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        *,
        artifact_goal: FarmGoal | None = None,
        preferences: str = "",
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
    ) -> RotationStrategyResult:
        evidence, _ = RotationEvidenceTool.execute(
            intent, profiles, artifact_goal, preferences
        )
        prompt = self._prompt(evidence)
        schema = RotationDraft.model_json_schema()
        payload = complete_json_with_truncation_retry(
            self.llm,
            LLMRequest(
                purpose="rotation_strategy",
                input_text=prompt,
                max_output_tokens=4_000,
                response_schema=schema,
                response_schema_name="rotation_strategy",
                reasoning_effort=reasoning_effort,
                web_search=True,
            ),
            recovery_input=(
                prompt
                + "\n\nThe previous generation was truncated. Return the complete JSON "
                "object again without Markdown or omitted fields."
            ),
            recovery_tokens=6_000,
            recovery_purpose="rotation_strategy_recovery",
            recovery_schema_name="rotation_strategy_recovery",
            operation_label="rotation strategy",
        )
        try:
            draft = RotationDraft.model_validate(payload)
            report = self.llm.report()
            web_research_used = any(
                call.web_search_used and call.status == "succeeded"
                for call in report.calls
            )
            if not web_research_used:
                raise ValueError("required web research for current kits and rotations did not run")
            draft, rotation, validation = RotationValidator.execute(
                draft,
                evidence,
                web_research_used=web_research_used,
            )
        except (ValidationError, ValueError) as exc:
            self.llm.invalidate_last_output(f"rotation validation failed: {exc}")
            raise RotationOutputError(
                f"Не удалось проверить предложенную ротацию: {exc}", self.llm.report()
            ) from exc
        return RotationStrategyResult(
            draft=draft,
            validated_rotation=rotation,
            validation=validation,
            evidence=evidence,
            llm_audit=report,
        )

    @staticmethod
    def _prompt(evidence: RotationEvidence) -> str:
        schema = RotationDraft.model_json_schema()
        return (
            RUSSIAN_UI_COPY_STYLE
            + "\n\nYou are the strategic rotation planner in GrindLess. Before producing the "
            "sequence, use web search to verify every member's current kit, cooldown/energy "
            "mechanics, recommended rotations and the exact reaction rules used by this team. "
            "Create a semantic "
            "rotation for exactly the confirmed domain_team. Use only allowed_actions "
            "and include every team member. Use repetitions instead of adjacent duplicate "
            "steps. Every burst step must have exactly one burst_fallback. Never emit key "
            "bindings, mouse actions, milliseconds, unverified damage numbers or claims that "
            "the plan is executable. Explain reasoning in Russian. The preferences field is a "
            "direct user instruction: apply it and explain the result or conflict in "
            "preference_handling_ru. Do not call a published mechanic unknown before searching "
            "for it. Record only uncertainty that remains after research in assumptions_ru. "
            "Return one JSON object and no Markdown.\n\nJSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            + "\n\nInput data:\n"
            + evidence.model_dump_json(exclude_none=False)
        )


def validate_resolved_rotation(rotation: ValidatedRotation, plan: TeamPlan) -> None:
    if len(plan.domain_team) != 4 or set(rotation.domain_team) != set(plan.domain_team):
        raise ValueError("rotation belongs to another domain team")
    if rotation.validation_level != "structural_only" or rotation.input_authority != "none":
        raise ValueError("rotation claims unsupported validation or input authority")
    if set(rotation.terminal_states) != {"rotation_complete", "safe_stop"}:
        raise ValueError("rotation terminal states are invalid")
    if rotation.entry_state != "step_01":
        raise ValueError("rotation entry or repeat state is invalid")
    state_ids = {state.state_id for state in rotation.states}
    if len(state_ids) != len(rotation.states):
        raise ValueError("rotation contains duplicate state ids")
    primary_states = [state for state in rotation.states if not state.recovery]
    if len(primary_states) < 4:
        raise ValueError("rotation contains too few primary states")
    expected_primary_ids = [_step_id(index) for index in range(1, len(primary_states) + 1)]
    if [state.state_id for state in primary_states] != expected_primary_ids:
        raise ValueError("rotation primary states are not contiguous or ordered")
    if rotation.repeat_state not in set(expected_primary_ids):
        raise ValueError("rotation entry or repeat state is invalid")
    if {state.character_key for state in primary_states} != set(rotation.domain_team):
        raise ValueError("rotation primary states do not cover the domain team")
    allowed_transitions = state_ids | set(rotation.terminal_states)
    for primary_index, state in enumerate(primary_states, start=1):
        if state.source_step != primary_index:
            raise ValueError("rotation primary state has an invalid source step")
        expected_success = (
            _step_id(primary_index + 1)
            if primary_index < len(primary_states)
            else "rotation_complete"
        )
        if state.on_success != expected_success:
            raise ValueError("rotation primary success transitions are invalid")

    for state in rotation.states:
        if state.character_key not in rotation.domain_team:
            raise ValueError("rotation state uses a character outside the domain team")
        if state.on_success not in allowed_transitions:
            raise ValueError("rotation state has an unknown success transition")
        if state.on_failure != "safe_stop":
            raise ValueError("rotation state can bypass safe_stop after failed confirmation")
        if (
            state.on_burst_unavailable is not None
            and state.on_burst_unavailable not in allowed_transitions
        ):
            raise ValueError("rotation state has an unknown burst fallback transition")
        if state.action != "burst" and state.on_burst_unavailable is not None:
            raise ValueError("non-burst state contains a burst fallback")
        if state.action == "burst" and state.on_burst_unavailable is None:
            raise ValueError("burst state has no unavailable fallback")
        if state.recovery:
            expected_id = f"recovery_{state.source_step:02d}_skill"
            if (
                state.state_id != expected_id
                or state.action != "skill"
                or state.repetitions != 1
                or state.on_success != _step_id(state.source_step)
                or state.on_burst_unavailable is not None
            ):
                raise ValueError("rotation recovery state is invalid")
            source = next(
                (item for item in primary_states if item.source_step == state.source_step),
                None,
            )
            if (
                source is None
                or source.action != "burst"
                or source.on_burst_unavailable != state.state_id
            ):
                raise ValueError("rotation recovery state has no burst source")
        elif state.state_id.startswith("recovery_"):
            raise ValueError("rotation disguises a recovery state as a primary state")
    if rotation.plan_fingerprint != _rotation_fingerprint(rotation):
        raise ValueError("rotation fingerprint does not match its compiled states")


def _step_id(index: int) -> str:
    return f"step_{index:02d}"


def _coverage(
    members: list[RotationMemberEvidence],
) -> Literal["curated", "partial", "identity_only"]:
    curated = sum(item.role_evidence == "curated" for item in members)
    if curated == len(members):
        return "curated"
    if curated == 0:
        return "identity_only"
    return "partial"


def _rotation_fingerprint(rotation: ValidatedRotation) -> str:
    payload = rotation.model_dump(mode="json", exclude={"plan_fingerprint"})
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()
