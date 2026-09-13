from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .character_catalog import (
    CHARACTERS,
    TARGET_PROFILES,
    TEAM_OBJECTIVE_DESCRIPTIONS,
    TeamIntent,
    TeamObjective,
    TeamPlan,
    build_team_plan,
)
from .enka import EnkaCharacterProfile
from .llm import (
    AuditedLLM,
    LLMBackend,
    LLMRequest,
    NarrationReport,
    ReasoningEffort,
)
from .prompt_style import RUSSIAN_UI_COPY_STYLE
from .structured_output import (
    StructuredOutputError,
    complete_json_with_truncation_retry,
)
from .team_evaluator import (
    TeamCandidateProposal,
    TeamEvaluationError,
    TeamEvaluationPair,
    TeamEvaluator,
)


class TeamStrategyRequest(BaseModel):
    team_intent: TeamIntent
    enka_collection_id: str = Field(min_length=16, max_length=256)
    llm_backend: LLMBackend
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    preferences: str = Field(default="", max_length=2_000)


class TeamCandidateEvidence(BaseModel):
    character_key: str
    name_ru: str
    element: str
    role: str
    role_evidence: Literal["curated", "identity_only"]
    character_level: int | None
    constellation: int
    skill_levels: dict[str, int]
    weapon_id: int | None
    weapon_level: int | None
    weapon_refinement: int | None


class TeamStrategyEvidence(BaseModel):
    target_key: str
    target_team_mode: str
    target_team: list[str]
    target_objective: TeamObjective
    target_objective_definition: str
    domain_team_mode: str
    domain_team: list[str]
    domain_objective: TeamObjective
    domain_objective_definition: str
    allowed_candidate_keys: list[str]
    candidates: list[TeamCandidateEvidence]
    preferences: str
    knowledge_limitations: list[str]
    domain_target_sets: list[str]
    domain_context_notice: str = (
        "Команда домена должна быть пригодна для доменов перечисленных наборов. "
        "Точный набор будет выбран следующим стратегическим шагом, поэтому исследуй "
        "актуальных противников и ограничения каждого варианта и явно отмечай компромисс."
    )
    privacy_notice: str = (
        "OpenAI получает выбранные поля Enka, цели команд и комментарий пользователя; "
        "веб-поиск отправляет поисковые запросы. UID, видео, GOOD и артефакты не передаются."
    )


class TeamStrategyDraft(BaseModel):
    target_objective: TeamObjective
    domain_objective: TeamObjective
    target_candidates: list[TeamCandidateProposal] = Field(min_length=1, max_length=5)
    domain_candidates: list[TeamCandidateProposal] = Field(min_length=1, max_length=5)
    recommendations_ru: list[str] = Field(default_factory=list, max_length=8)
    preference_handling_ru: str = Field(default="", max_length=1_000)
    assumptions_ru: list[str] = Field(default_factory=list, max_length=8)
    confidence: Literal["high", "medium", "low"]


class StrategyValidation(BaseModel):
    passed: bool = True
    checks: list[str]
    knowledge_coverage: Literal[
        "curated", "partial", "identity_only", "web_researched"
    ]


class TeamStrategyResult(BaseModel):
    decision_owner: Literal["llm_plus_team_evaluator"] = "llm_plus_team_evaluator"
    execution_status: Literal["shadow_only"] = "shadow_only"
    target_team: list[str]
    domain_team: list[str]
    target_strategy_ru: str
    domain_strategy_ru: str
    synergies_ru: list[str]
    weak_points_ru: list[str]
    recommendations_ru: list[str]
    preference_handling_ru: str
    assumptions_ru: list[str]
    confidence: Literal["high", "medium", "low"]
    evaluation: TeamEvaluationPair
    validated_team_plan: TeamPlan
    validation: StrategyValidation
    evidence: TeamStrategyEvidence
    llm_audit: NarrationReport


StrategyOutputError = StructuredOutputError


class TeamEvidenceTool:
    """Build the only account evidence the first strategic model call may see."""

    @staticmethod
    def execute(
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        preferences: str,
    ) -> TeamStrategyEvidence:
        preliminary = build_team_plan(intent)
        expected = set(preliminary.expected_showcase_keys)
        by_key = {profile.character_key: profile for profile in profiles}
        missing = sorted(expected - set(by_key))
        if missing:
            raise ValueError(
                "В загруженных витринах Enka не найдены обязательные персонажи: "
                + ", ".join(missing)
            )

        evidence: list[TeamCandidateEvidence] = []
        identity_only: list[str] = []
        for key in sorted(expected):
            definition = CHARACTERS[key]
            profile = by_key[key]
            curated = definition.role != "team candidate"
            if not curated:
                identity_only.append(key)
            evidence.append(
                TeamCandidateEvidence(
                    character_key=key,
                    name_ru=definition.name_ru,
                    element=definition.element,
                    role=definition.role,
                    role_evidence="curated" if curated else "identity_only",
                    character_level=profile.character_level,
                    constellation=profile.constellation,
                    skill_levels=profile.skill_levels,
                    weapon_id=profile.weapon_id,
                    weapon_level=profile.weapon_level,
                    weapon_refinement=profile.weapon_refinement,
                )
            )

        limitations = []
        if identity_only:
            limitations.append(
                "В локальной базе пока нет подробного описания роли для: "
                + ", ".join(identity_only)
                + ". Роль и актуальные команды нужно проверить по свежим источникам."
            )
        return TeamStrategyEvidence(
            target_key=intent.target_key,
            target_team_mode=intent.target_team_mode,
            target_team=intent.target_team,
            target_objective=preliminary.target_objective,
            target_objective_definition=TEAM_OBJECTIVE_DESCRIPTIONS[
                preliminary.target_objective
            ],
            domain_team_mode=intent.domain_team_mode,
            domain_team=intent.domain_team,
            domain_objective=preliminary.domain_objective,
            domain_objective_definition=TEAM_OBJECTIVE_DESCRIPTIONS[
                preliminary.domain_objective
            ],
            allowed_candidate_keys=intent.candidate_pool,
            candidates=evidence,
            preferences=preferences.strip(),
            knowledge_limitations=limitations,
            domain_target_sets=list(dict.fromkeys(
                requirement.set_name
                for option in TARGET_PROFILES[intent.target_key].set_options
                for requirement in option.requirements
            )),
        )


class TeamStrategyValidator:
    """Validate model-owned choices without replacing their strategic meaning."""

    @staticmethod
    def execute(
        draft: TeamStrategyDraft,
        target_candidate: TeamCandidateProposal,
        domain_candidate: TeamCandidateProposal,
        intent: TeamIntent,
        evidence: TeamStrategyEvidence,
        *,
        web_research_used: bool = False,
    ) -> tuple[TeamPlan, StrategyValidation, Literal["high", "medium", "low"], list[str]]:
        target_team = target_candidate.team
        domain_team = domain_candidate.team
        observed = {item.character_key for item in evidence.candidates}
        checks: list[str] = []

        TeamStrategyValidator._unique_four("целевая команда", target_team)
        TeamStrategyValidator._unique_four("команда домена", domain_team)
        if draft.target_objective != intent.target_objective:
            raise ValueError("В результате изменилась выбранная цель основной команды")
        if draft.domain_objective != intent.domain_objective:
            raise ValueError("В результате изменилась выбранная цель команды домена")
        checks.append("приоритеты обеих команд сохранены")
        if evidence.preferences and len(draft.preference_handling_ru.strip()) < 10:
            raise ValueError(
                "Не указано, как учтён ваш комментарий"
            )
        if evidence.preferences:
            checks.append("ваш комментарий учтён в результате")
        if intent.target_key not in target_team:
            raise ValueError("Основная команда не содержит выбранного персонажа")

        if intent.target_team_mode == "manual":
            if set(target_team) != set(intent.target_team):
                raise ValueError("В результате изменился указанный вами основной состав")
            checks.append("указанный вами основной состав сохранён")
        else:
            allowed_target = set(intent.candidate_pool) | {intent.target_key}
            if not set(target_team) <= allowed_target:
                raise ValueError("целевая команда вышла за явно разрешённый пул")
            checks.append("основная команда собрана только из выбранных персонажей")

        if intent.domain_team_mode == "same":
            if set(domain_team) != set(target_team):
                raise ValueError("Для режима «Та же команда» получились разные составы")
            domain_team = list(target_team)
            checks.append("для обеих целей используется один состав")
        elif intent.domain_team_mode == "manual":
            if set(domain_team) != set(intent.domain_team):
                raise ValueError("В результате изменился указанный вами состав домена")
            checks.append("указанный вами состав домена сохранён")
        else:
            allowed_domain = set(intent.candidate_pool) | {intent.target_key}
            if not set(domain_team) <= allowed_domain:
                raise ValueError("команда домена вышла за явно разрешённый пул")
            checks.append("команда домена собрана только из выбранных персонажей")
            checks.append("команда домена подобрана независимо от основного состава")

        if not set(target_team + domain_team) <= observed:
            unknown = sorted(set(target_team + domain_team) - observed)
            raise ValueError(
                "В состав попали персонажи, которых нет в загруженных витринах Enka: "
                + ", ".join(unknown)
            )
        checks.append("в каждой команде четыре разных персонажа из Enka")

        resolved_intent = TeamIntent(
            target_key=intent.target_key,
            target_objective=intent.target_objective,
            target_team_mode="manual",
            target_team=target_team,
            domain_team_mode=(
                "same" if intent.domain_team_mode == "same" else "manual"
            ),
            domain_objective=intent.domain_objective,
            domain_team=([] if intent.domain_team_mode == "same" else domain_team),
            candidate_pool=[],
        )
        plan = build_team_plan(resolved_intent)

        selected = set(target_team + domain_team)
        selected_evidence = [
            item for item in evidence.candidates if item.character_key in selected
        ]
        curated_count = sum(
            item.role_evidence == "curated" for item in selected_evidence
        )
        if curated_count == len(selected_evidence):
            coverage: Literal[
                "curated", "partial", "identity_only", "web_researched"
            ] = "curated"
        elif web_research_used:
            coverage = "web_researched"
        elif curated_count == 0:
            coverage = "identity_only"
        else:
            coverage = "partial"

        assumptions = list(draft.assumptions_ru)
        confidence = draft.confidence
        if coverage not in {"curated", "web_researched"}:
            confidence = "low"
            assumptions.append(
                "Для части персонажей в локальной базе пока нет полного описания роли. "
                "Перед использованием команды перепроверьте их актуальные механики."
            )
        return plan, StrategyValidation(
            checks=checks,
            knowledge_coverage=coverage,
        ), confidence, list(dict.fromkeys(assumptions))

    @staticmethod
    def _unique_four(label: str, values: list[str]) -> None:
        if len(values) != 4 or len(set(values)) != 4:
            raise ValueError(f"{label} должна содержать четыре разных персонажа")


class TeamStrategist:
    def __init__(self, llm: AuditedLLM, evaluator: TeamEvaluator | None = None) -> None:
        self.llm = llm
        self.evaluator = evaluator or TeamEvaluator()

    def plan(
        self,
        intent: TeamIntent,
        profiles: list[EnkaCharacterProfile],
        preferences: str = "",
        reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM,
    ) -> TeamStrategyResult:
        evidence = TeamEvidenceTool.execute(intent, profiles, preferences)
        prompt = self._prompt(evidence)
        schema = TeamStrategyDraft.model_json_schema()
        evaluation: TeamEvaluationPair | None = None
        target_candidate: TeamCandidateProposal | None = None
        domain_candidate: TeamCandidateProposal | None = None
        draft: TeamStrategyDraft | None = None
        for quality_attempt in range(2):
            purpose = (
                "account_and_team_strategy"
                if quality_attempt == 0
                else "account_and_team_strategy_quality_retry"
            )
            payload = self._complete_draft(
                prompt,
                schema,
                reasoning_effort,
                purpose=purpose,
            )
            try:
                draft = TeamStrategyDraft.model_validate(payload)
                latest_call = self.llm.calls[-1]
                if not latest_call.web_search_used or latest_call.status != "succeeded":
                    raise ValueError("обязательный веб-поиск по игровым механикам не выполнен")
                target_candidate, domain_candidate, evaluation = self.evaluator.evaluate_pair(
                    target_candidates=draft.target_candidates,
                    domain_candidates=draft.domain_candidates,
                    intent=intent,
                    observed_keys={item.character_key for item in evidence.candidates},
                    preferences=evidence.preferences,
                )
                break
            except TeamEvaluationError as exc:
                self.llm.invalidate_last_output(f"team evaluation failed: {exc.feedback_ru()}")
                if quality_attempt == 0:
                    prompt = self._quality_retry_prompt(evidence, exc.feedback_ru())
                    continue
                raise StrategyOutputError(
                    "Не удалось подобрать подходящие команды: " + exc.feedback_ru(),
                    self.llm.report(),
                ) from exc
            except (ValidationError, ValueError) as exc:
                self.llm.invalidate_last_output(f"strategy validation failed: {exc}")
                raise StrategyOutputError(
                    f"Не удалось проверить предложенные команды: {exc}", self.llm.report()
                ) from exc

        if draft is None or target_candidate is None or domain_candidate is None or evaluation is None:
            raise RuntimeError("Не удалось выбрать подходящую пару команд")
        try:
            plan, validation, confidence, assumptions = TeamStrategyValidator.execute(
                draft,
                target_candidate,
                domain_candidate,
                intent,
                evidence,
                web_research_used=True,
            )
        except ValueError as exc:
            self.llm.invalidate_last_output(f"strategy validation failed: {exc}")
            raise StrategyOutputError(
                f"Не удалось проверить предложенные команды: {exc}", self.llm.report()
            ) from exc
        validation.checks.append("альтернативные составы сравнены по одной шкале")
        report = self.llm.report()
        return TeamStrategyResult(
            target_team=target_candidate.team,
            domain_team=(
                target_candidate.team
                if intent.domain_team_mode == "same"
                else domain_candidate.team
            ),
            target_strategy_ru=target_candidate.strategy_ru,
            domain_strategy_ru=domain_candidate.strategy_ru,
            synergies_ru=list(dict.fromkeys(
                target_candidate.synergies_ru + domain_candidate.synergies_ru
            ))[:8],
            weak_points_ru=list(dict.fromkeys(
                target_candidate.weak_points_ru + domain_candidate.weak_points_ru
            ))[:8],
            recommendations_ru=draft.recommendations_ru,
            preference_handling_ru=draft.preference_handling_ru,
            assumptions_ru=assumptions,
            confidence=confidence,
            evaluation=evaluation,
            validated_team_plan=plan,
            validation=validation,
            evidence=evidence,
            llm_audit=report,
        )

    def _complete_draft(
        self,
        prompt: str,
        schema: dict[str, object],
        reasoning_effort: ReasoningEffort,
        *,
        purpose: str,
    ) -> object:
        return complete_json_with_truncation_retry(
            self.llm,
            LLMRequest(
                purpose=purpose,
                input_text=prompt,
                max_output_tokens=6_000,
                response_schema=schema,
                response_schema_name="team_strategy",
                reasoning_effort=reasoning_effort,
                web_search=True,
            ),
            recovery_input=(
                prompt
                + "\n\nПредыдущая генерация оборвалась. Верни полный JSON-объект "
                "целиком; не сокращай и не добавляй Markdown."
            ),
            recovery_tokens=8_000,
            recovery_purpose=f"{purpose}_truncation_recovery",
            recovery_schema_name="team_strategy_recovery",
            operation_label="стратегия команд",
        )

    @staticmethod
    def _quality_retry_prompt(evidence: TeamStrategyEvidence, feedback_ru: str) -> str:
        return (
            TeamStrategist._prompt(evidence)
            + "\n\nTeamEvaluator отклонил предыдущий результат. Исправь именно эти "
            "проблемы и предложи новые допустимые альтернативы:\n"
            + feedback_ru
        )

    @staticmethod
    def _prompt(evidence: TeamStrategyEvidence) -> str:
        schema = TeamStrategyDraft.model_json_schema()
        return (
            RUSSIAN_UI_COPY_STYLE
            + "\n\nТы — стратегический агент GrindLess. До выбора команд обязательно используй "
            "веб-поиск: проверь актуальные описания навыков, реакций, роли и современные "
            "командные гайды для каждого реального кандидата. Отделяй данные аккаунта из "
            "входных данных от публичных игровых знаний из найденных источников. Ручные "
            "составы нельзя менять. При auto "
            "можно выбирать только из allowed_candidate_keys и target_key. Строго "
            "сравни несколько допустимых составов по синергии реакций, фактическим ролям, "
            "стоимости энергии, удобству и повторяемости ротации; не выбирай состав только "
            "по редкости персонажей. Отбрасывай несовместимые или заведомо слабые связки и "
            "объясни конкретное преимущество каждого кандидата. Для каждого auto-состава "
            "верни минимум две разные альтернативы, если разрешённый пул допускает больше "
            "одной комбинации; для manual достаточно одной. Заполни rubric оценками 0–5 "
            "только после поиска: mechanics_verified=true допустимо лишь когда актуальные "
            "механики всех четырёх персонажей проверены. Rubric — сравнительная шкала: не "
            "указывай проценты или точные значения урона. Для domain_candidates исследуй домены всех наборов из "
            "domain_target_sets: текущих противников, сопротивления, волны и ограничения; "
            "отрази пригодность в domain_compatibility. Локальный TeamEvaluator сам применит "
            "веса, пороги и выберет "
            "победителя. "
            "соблюдай target_objective и domain_objective и верни их без изменений; "
            "их точные определения находятся в полях *_objective_definition. Если "
            "domain_team_mode=\"same\", верни одинаковый состав, но отдельно объясни, "
            "как он отвечает каждой из двух целей и какой компромисс возникает. Не указывай "
            "уровни, оружие или численные результаты, которых нет во входных данных. При domain_team_mode=\"auto\" "
            "команда домена выбирается независимо из всех allowed_candidate_keys: target_key "
            "можно использовать, но включать его не обязательно. Поле preferences — прямое "
            "указание пользователя: исполни его, если оно не конфликтует с жёсткими границами, "
            "и явно опиши результат или конфликт в preference_handling_ru. Не называй игровую "
            "механику неизвестной, пока не попытался найти её в интернете. Если после поиска "
            "факт всё ещё неясен, запиши его в assumptions_ru и снизь confidence. Верни только один "
            "JSON-объект без Markdown.\n\nJSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, sort_keys=True)
            + "\n\nВходные данные:\n"
            + evidence.model_dump_json(exclude_none=False)
        )
