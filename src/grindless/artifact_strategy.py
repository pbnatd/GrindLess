from __future__ import annotations

import json
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .character_catalog import (
    CHARACTERS,
    TARGET_PROFILES,
    TargetBenchmark,
    TargetSetOption,
    TeamIntent,
    TeamPlan,
    build_team_plan,
    character_goal,
)
from .enka import EnkaCharacterProfile
from .good_import import GoodInventory, import_good
from .llm import (
    AuditedLLM,
    LLMBackend,
    LLMRequest,
    NarrationReport,
    ReasoningEffort,
)
from .prompt_style import RUSSIAN_UI_COPY_STYLE
from .models import (
    BaselineMode,
    BuildConstraints,
    FarmGoal,
    FarmPolicy,
    InitialBuildAudit,
    Slot,
    SlotGoal,
    Stat,
)
from .optimizer import BruteForceBuildOptimizer
from .structured_output import StructuredOutputError, complete_json_with_truncation_retry


class ArtifactGoalRequest(BaseModel):
    inventory: dict[str, Any]
    team_intent: TeamIntent
    enka_collection_id: str = Field(min_length=16, max_length=256)
    llm_backend: LLMBackend
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    policy: FarmPolicy = FarmPolicy.ECONOMY
    preferences: str = Field(default="", max_length=2_000)


class ArtifactObservation(BaseModel):
    set_name: str
    slot: Slot
    level: int
    main_stat: Stat
    substats: list[Stat]
    equipped_on_target: bool


class ArtifactTeamMemberEvidence(BaseModel):
    character_key: str
    element: str
    role: str
    role_evidence: Literal["curated", "identity_only"]
    constellation: int
    skill_levels: dict[str, int]


class ArtifactTargetEvidence(BaseModel):
    character_key: str
    name_ru: str
    element: str
    role: str
    enka_level: int | None
    constellation: int
    skill_levels: dict[str, int]
    good_level: int | None
    good_ascension: int | None
    good_talents: dict[str, int] | None
    weapon_key: str | None
    weapon_level: int | None
    weapon_refinement: int | None


class ArtifactGoalEvidence(BaseModel):
    target: ArtifactTargetEvidence
    target_team: list[str]
    domain_team: list[str]
    team_members: list[ArtifactTeamMemberEvidence]
    allowed_set_options: list[TargetSetOption]
    allowed_main_stats: dict[Slot, list[Stat]]
    valid_substats: list[Stat]
    local_profile_reference: list[SlotGoal]
    profile_source_url: str
    profile_source_version: str
    profile_benchmarks: list[TargetBenchmark]
    profile_caveats_ru: list[str]
    inventory_artifact_count: int
    curated_set_counts: dict[str, int]
    candidate_observations: dict[Slot, list[ArtifactObservation]]
    preferences: str
    knowledge_limitations: list[str]
    privacy_notice: str = (
        "OpenAI receives a compact typed projection: the confirmed team, target profile, "
        "user comment, equipped weapon name when GOOD contains it, and at most six artifact "
        "observations per slot. Web search sends search queries. The raw GOOD document, UID "
        "and video are not transmitted."
    )


class ArtifactSlotDraft(BaseModel):
    slot: Slot
    allowed_main_stats: list[Stat] = Field(min_length=1, max_length=3)
    min_useful_substats: int = Field(ge=1, le=4)
    rationale_ru: str = Field(min_length=20, max_length=700)


class ArtifactGoalDraft(BaseModel):
    build_role_ru: str = Field(min_length=20, max_length=1_000)
    selected_set_option_id: str = Field(pattern=r"^[a-z0-9_]{3,80}$")
    slots: list[ArtifactSlotDraft] = Field(min_length=5, max_length=5)
    substat_priority_order: list[Stat] = Field(min_length=3, max_length=8)
    slot_priority_order: list[Slot] = Field(min_length=5, max_length=5)
    farming_plan_ru: str = Field(min_length=20, max_length=1_500)
    alternative_upgrade_ru: str = Field(min_length=20, max_length=1_000)
    preference_handling_ru: str = Field(default="", max_length=1_000)
    assumptions_ru: list[str] = Field(default_factory=list, max_length=8)
    confidence: Literal["high", "medium", "low"]


class ArtifactGoalValidation(BaseModel):
    passed: Literal[True] = True
    checks: list[str]
    evaluation_mode: Literal["content_only"] = "content_only"
    off_piece_status: Literal["optimized_locally"] = "optimized_locally"


class ArtifactGoalResult(BaseModel):
    decision_owner: Literal["llm"] = "llm"
    execution_status: Literal["shadow_only"] = "shadow_only"
    draft: ArtifactGoalDraft
    resolved_goal: FarmGoal
    inventory_audit: InitialBuildAudit
    validation: ArtifactGoalValidation
    evidence: ArtifactGoalEvidence
    llm_audit: NarrationReport


ArtifactGoalOutputError = StructuredOutputError


_SUBSTAT_STATS = {
    Stat.HP_FLAT,
    Stat.ATK_FLAT,
    Stat.DEF_FLAT,
    Stat.HP_PCT,
    Stat.ATK_PCT,
    Stat.DEF_PCT,
    Stat.ELEMENTAL_MASTERY,
    Stat.ENERGY_RECHARGE,
    Stat.CRIT_RATE,
    Stat.CRIT_DMG,
}

_ELEMENT_DAMAGE = {
    "Pyro": Stat.PYRO_DMG,
    "Hydro": Stat.HYDRO_DMG,
    "Electro": Stat.ELECTRO_DMG,
    "Cryo": Stat.CRYO_DMG,
    "Anemo": Stat.ANEMO_DMG,
    "Geo": Stat.GEO_DMG,
    "Dendro": Stat.DENDRO_DMG,
}


def allowed_main_stats_for(element: str) -> dict[Slot, set[Stat]]:
    goblet = {
        Stat.HP_PCT,
        Stat.ATK_PCT,
        Stat.DEF_PCT,
        Stat.ELEMENTAL_MASTERY,
        Stat.PHYSICAL_DMG,
    }
    damage = _ELEMENT_DAMAGE.get(element)
    if damage is not None:
        goblet.add(damage)
    return {
        Slot.FLOWER: {Stat.HP_FLAT},
        Slot.PLUME: {Stat.ATK_FLAT},
        Slot.SANDS: {
            Stat.HP_PCT,
            Stat.ATK_PCT,
            Stat.DEF_PCT,
            Stat.ELEMENTAL_MASTERY,
            Stat.ENERGY_RECHARGE,
        },
        Slot.GOBLET: goblet,
        Slot.CIRCLET: {
            Stat.HP_PCT,
            Stat.ATK_PCT,
            Stat.DEF_PCT,
            Stat.ELEMENTAL_MASTERY,
            Stat.CRIT_RATE,
            Stat.CRIT_DMG,
            Stat.HEALING_BONUS,
        },
    }


class ArtifactEvidenceTool:
    """Project GOOD and Enka into the bounded evidence for artifact planning."""

    @staticmethod
    def execute(
        inventory_payload: dict[str, Any],
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        policy: FarmPolicy,
        preferences: str,
    ) -> tuple[ArtifactGoalEvidence, GoodInventory, TeamPlan]:
        definition = CHARACTERS.get(intent.target_key)
        if definition is None or not definition.full_target_support:
            raise ValueError(f"unsupported target character: {intent.target_key}")
        plan = build_team_plan(intent)
        if plan.target_team_status != "confirmed" or plan.domain_team_status == "pending_optimizer":
            raise ValueError(
                "artifact planning requires confirmed teams; build the team strategy first"
            )

        by_key = {profile.character_key: profile for profile in profiles}
        selected_keys = set(plan.target_team + plan.domain_team)
        missing = sorted(selected_keys - set(by_key))
        if missing:
            raise ValueError(
                "Enka collection does not confirm selected team members: "
                + ", ".join(missing)
            )
        target_profile = by_key.get(intent.target_key)
        if target_profile is None:
            raise ValueError("Enka collection does not contain the target character")

        imported = import_good(inventory_payload)
        if not imported.artifacts:
            raise ValueError("GOOD contains no artifacts")
        good_character = imported.character(intent.target_key)
        equipped_weapon = imported.equipped_weapon(intent.target_key)
        limitations = [
            "Артефакты сравниваются на текущем уровне, без улучшения до +20.",
            "Требования к восстановлению энергии уточняются после настройки ротации.",
            "Комплект и пятый свободный предмет подбираются по всему загруженному инвентарю.",
            "Целевые значения зависят от команды и служат ориентиром, а не обязательным минимумом.",
        ]
        if good_character is None:
            limitations.append(
                "В GOOD нет записи о целевом персонаже, поэтому уровень и таланты взяты из Enka."
            )
        if equipped_weapon is None:
            limitations.append(
                "В GOOD не указано название экипированного оружия. Проверьте его перед финальным выбором сборки."
            )

        profile = TARGET_PROFILES[intent.target_key]
        set_options = profile.set_options
        curated_sets = list(dict.fromkeys(
            requirement.set_name
            for option in set_options
            for requirement in option.requirements
        ))
        reference = character_goal(intent.target_key, policy)
        allowed_main = {
            item.slot: set(item.allowed_main_stats) for item in reference.targets
        }
        observations: dict[Slot, list[ArtifactObservation]] = {}
        for slot in Slot:
            target = next(item for item in reference.targets if item.slot == slot)
            candidates = [
                item
                for item in imported.artifacts
                if item.slot == slot and item.rarity == 5
            ]
            candidates.sort(
                key=lambda item: (
                    item.main_stat not in target.allowed_main_stats,
                    -len({sub.stat for sub in item.known_substats} & set(target.substat_priorities)),
                    -item.level,
                    -len(item.known_substats),
                    item.set_name not in curated_sets,
                    item.set_name,
                    item.source_index or 10**9,
                )
            )
            observations[slot] = [
                ArtifactObservation(
                    set_name=item.set_name,
                    slot=item.slot,
                    level=item.level,
                    main_stat=item.main_stat,
                    substats=[substat.stat for substat in item.known_substats],
                    equipped_on_target=item.equipped_by == intent.target_key,
                )
                for item in candidates[:6]
            ]

        counts = Counter(
            item.set_name for item in imported.artifacts if item.set_name in curated_sets
        )
        evidence = ArtifactGoalEvidence(
            target=ArtifactTargetEvidence(
                character_key=definition.key,
                name_ru=definition.name_ru,
                element=definition.element,
                role=definition.role,
                enka_level=target_profile.character_level,
                constellation=target_profile.constellation,
                skill_levels=target_profile.skill_levels,
                good_level=good_character.level if good_character else None,
                good_ascension=good_character.ascension if good_character else None,
                good_talents=(
                    good_character.talents.model_dump(mode="json")
                    if good_character and good_character.talents
                    else None
                ),
                weapon_key=equipped_weapon.key if equipped_weapon else None,
                weapon_level=equipped_weapon.level if equipped_weapon else target_profile.weapon_level,
                weapon_refinement=(
                    equipped_weapon.refinement
                    if equipped_weapon
                    else target_profile.weapon_refinement
                ),
            ),
            target_team=plan.target_team,
            domain_team=plan.domain_team,
            team_members=[
                ArtifactTeamMemberEvidence(
                    character_key=key,
                    element=CHARACTERS[key].element,
                    role=CHARACTERS[key].role,
                    role_evidence=(
                        "curated" if CHARACTERS[key].role != "team candidate" else "identity_only"
                    ),
                    constellation=by_key[key].constellation,
                    skill_levels=by_key[key].skill_levels,
                )
                for key in sorted(selected_keys)
            ],
            allowed_set_options=set_options,
            allowed_main_stats={
                slot: sorted(values, key=str) for slot, values in allowed_main.items()
            },
            valid_substats=sorted(_SUBSTAT_STATS, key=str),
            local_profile_reference=reference.targets,
            profile_source_url=profile.source_url,
            profile_source_version=profile.source_version,
            profile_benchmarks=profile.benchmarks,
            profile_caveats_ru=profile.caveats_ru,
            inventory_artifact_count=len(imported.artifacts),
            curated_set_counts={key: counts.get(key, 0) for key in curated_sets},
            candidate_observations=observations,
            preferences=preferences.strip(),
            knowledge_limitations=limitations,
        )
        return evidence, imported, plan


class ArtifactGoalValidator:
    @staticmethod
    def execute(
        draft: ArtifactGoalDraft,
        evidence: ArtifactGoalEvidence,
        policy: FarmPolicy,
    ) -> tuple[FarmGoal, ArtifactGoalValidation]:
        options = {
            option.option_id: option for option in evidence.allowed_set_options
        }
        selected_option = options.get(draft.selected_set_option_id)
        if selected_option is None:
            raise ValueError("model selected an artifact set option outside the curated profile")
        if evidence.preferences and len(draft.preference_handling_ru.strip()) < 10:
            raise ValueError(
                "model did not explain how the user comment affected the artifact goal"
            )
        if len(draft.substat_priority_order) != len(set(draft.substat_priority_order)):
            raise ValueError("substat priority order contains duplicates")
        if not set(draft.substat_priority_order) <= _SUBSTAT_STATS:
            raise ValueError("substat priority order contains impossible artifact substats")
        if len(draft.slot_priority_order) != len(set(draft.slot_priority_order)) or set(
            draft.slot_priority_order
        ) != set(Slot):
            raise ValueError("slot priority order must contain every slot exactly once")

        allowed_main = {
            slot: set(stats) for slot, stats in evidence.allowed_main_stats.items()
        }
        by_slot: dict[Slot, ArtifactSlotDraft] = {}
        for item in draft.slots:
            if item.slot in by_slot:
                raise ValueError(f"model repeated slot {item.slot.value}")
            if len(item.allowed_main_stats) != len(set(item.allowed_main_stats)):
                raise ValueError(f"slot {item.slot.value} repeats a main stat")
            if not set(item.allowed_main_stats) <= allowed_main[item.slot]:
                raise ValueError(
                    f"slot {item.slot.value} contains a main stat outside the curated profile"
                )
            by_slot[item.slot] = item
        if set(by_slot) != set(Slot):
            raise ValueError("model must return all five artifact slots")
        if by_slot[Slot.FLOWER].allowed_main_stats != [Stat.HP_FLAT]:
            raise ValueError("flower main stat must be hp_flat")
        if by_slot[Slot.PLUME].allowed_main_stats != [Stat.ATK_FLAT]:
            raise ValueError("plume main stat must be atk_flat")

        substat_weights = {
            stat: float(len(draft.substat_priority_order) - index)
            for index, stat in enumerate(draft.substat_priority_order)
        }
        targets = []
        for slot in Slot:
            item = by_slot[slot]
            targets.append(
                SlotGoal(
                    slot=slot,
                    allowed_main_stats=set(item.allowed_main_stats),
                    main_stat_priorities={
                        stat: len(item.allowed_main_stats) - index
                        for index, stat in enumerate(item.allowed_main_stats)
                    },
                    substat_priorities=substat_weights,
                    min_useful_substats=item.min_useful_substats,
                    min_content_score_gain=1,
                    min_gain=0.01,
                )
            )
        goal = FarmGoal(
            character=evidence.target.character_key,
            targets=targets,
            policy=policy,
            constraints=BuildConstraints(
                stat_weights=substat_weights,
                set_requirements=selected_option.requirements,
            ),
            baseline_mode=BaselineMode.EMPTY,
        )
        return goal, ArtifactGoalValidation(
            checks=[
                "выбран подходящий комплект из 4 предметов или сочетание 2+2",
                "главные характеристики подходят всем пяти слотам",
                "дополнительные характеристики могут выпасть в игре",
                "каждый слот указан в плане ровно один раз",
                "все пять слотов подобраны как единая сборка",
                "свободный предмет выбран из всего загруженного инвентаря",
            ]
        )


class ArtifactGoalPlanner:
    def __init__(self, llm: AuditedLLM) -> None:
        self.llm = llm

    def plan(
        self,
        inventory_payload: dict[str, Any],
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        *,
        policy: FarmPolicy = FarmPolicy.ECONOMY,
        preferences: str = "",
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
    ) -> ArtifactGoalResult:
        evidence, imported, _ = ArtifactEvidenceTool.execute(
            inventory_payload, intent, profiles, policy, preferences
        )
        prompt = self._prompt(evidence)
        schema = ArtifactGoalDraft.model_json_schema()
        payload = complete_json_with_truncation_retry(
            self.llm,
            LLMRequest(
                purpose="artifact_goal_strategy",
                input_text=prompt,
                max_output_tokens=4_000,
                response_schema=schema,
                response_schema_name="artifact_goal_strategy",
                reasoning_effort=reasoning_effort,
                web_search=True,
            ),
            recovery_input=(
                prompt
                + "\n\nThe previous generation was truncated. Return the complete JSON object "
                "again without Markdown or omitted fields."
            ),
            recovery_tokens=6_000,
            recovery_purpose="artifact_goal_strategy_recovery",
            recovery_schema_name="artifact_goal_strategy_recovery",
            operation_label="artifact goal strategy",
        )
        try:
            draft = ArtifactGoalDraft.model_validate(payload)
            report = self.llm.report()
            if not any(
                call.web_search_used and call.status == "succeeded"
                for call in report.calls
            ):
                raise ValueError("required web research for current build knowledge did not run")
            goal, validation = ArtifactGoalValidator.execute(draft, evidence, policy)
            audit = BruteForceBuildOptimizer().audit_initial_build(
                imported.artifacts, goal, top_per_slot=5
            )
        except (ValidationError, ValueError) as exc:
            self.llm.invalidate_last_output(f"artifact goal validation failed: {exc}")
            raise ArtifactGoalOutputError(
                f"Не удалось проверить предложенную сборку: {exc}", self.llm.report()
            ) from exc
        return ArtifactGoalResult(
            draft=draft,
            resolved_goal=goal,
            inventory_audit=audit,
            validation=validation,
            evidence=evidence,
            llm_audit=report,
        )

    @staticmethod
    def _prompt(evidence: ArtifactGoalEvidence) -> str:
        schema = ArtifactGoalDraft.model_json_schema()
        return (
            RUSSIAN_UI_COPY_STYLE
            + "\n\nYou are the strategic artifact planner in GrindLess. Before deciding, use web "
            "search to verify the current character kit, reaction rules, team-dependent build "
            "guides and artifact recommendations. Decide the artifact "
            "goal for the confirmed target and team. Choose exactly one "
            "selected_set_option_id from allowed_set_options and use only legal main "
            "stats and valid_substats from the input data. Return every slot exactly once. "
            "The order of allowed_main_stats is a preference order; the order of "
            "substat_priority_order and slot_priority_order is also meaningful. Never "
            "infer a weapon name from a numeric Enka id, estimate upgrade outcomes, promise a "
            "damage increase, or claim an ER breakpoint before rotation validation. "
            "Explain reasoning in Russian. The preferences field is a direct user instruction: "
            "apply it when it does not conflict with the fixed validation rules, and state exactly "
            "how it affected the result or why it conflicts in preference_handling_ru. Do not "
            "call a public game mechanic unknown before attempting web research. When facts "
            "remain missing after search, record the uncertainty in assumptions_ru and lower confidence. "
            "Return one JSON object and no Markdown.\n\nJSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            + "\n\nInput data:\n"
            + evidence.model_dump_json(exclude_none=False)
        )


def validate_resolved_artifact_goal(
    goal: FarmGoal,
    *,
    target_key: str,
) -> None:
    definition = CHARACTERS.get(target_key)
    if definition is None or not definition.full_target_support:
        raise ValueError(f"unsupported target character: {target_key}")
    if goal.character != target_key:
        raise ValueError("artifact goal belongs to another character")
    profile = TARGET_PROFILES[target_key]
    allowed_compositions = {
        tuple(sorted((item.set_name, item.pieces) for item in option.requirements))
        for option in profile.set_options
    }
    composition = tuple(sorted(
        (item.set_name, item.pieces)
        for item in goal.constraints.set_requirements
    ))
    if composition not in allowed_compositions:
        raise ValueError("artifact goal requires a set composition outside the curated options")
    if len(goal.targets) != 5 or {item.slot for item in goal.targets} != set(Slot):
        raise ValueError("artifact goal must contain every slot exactly once")
    reference = character_goal(target_key, FarmPolicy.ECONOMY)
    allowed_main = {
        item.slot: set(item.allowed_main_stats) for item in reference.targets
    }
    for target in goal.targets:
        if target.allowed_sets:
            raise ValueError("artifact slots must leave the exact off-piece unrestricted")
        if not target.allowed_main_stats or not target.allowed_main_stats <= allowed_main[target.slot]:
            raise ValueError(f"artifact goal has illegal main stats for {target.slot.value}")
        if not set(target.substat_priorities) <= _SUBSTAT_STATS:
            raise ValueError("artifact goal contains impossible substats")
