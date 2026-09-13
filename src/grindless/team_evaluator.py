from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .character_catalog import CHARACTERS, TeamIntent, TeamObjective

TeamScope = Literal["target", "domain"]
TeamMetric = Literal[
    "damage_potential",
    "reaction_coherence",
    "rotation_stability",
    "energy_feasibility",
    "comfort",
    "account_readiness",
    "domain_compatibility",
]


class TeamRubricEvidence(BaseModel):
    """Finite claims researched by the model; the local evaluator owns their weights."""

    damage_potential: int = Field(ge=0, le=5)
    reaction_coherence: int = Field(ge=0, le=5)
    rotation_stability: int = Field(ge=0, le=5)
    energy_feasibility: int = Field(ge=0, le=5)
    comfort: int = Field(ge=0, le=5)
    account_readiness: int = Field(ge=0, le=5)
    domain_compatibility: int = Field(ge=0, le=5)
    mechanics_verified: bool
    evidence_ru: list[str] = Field(min_length=2, max_length=8)


class TeamCandidateProposal(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    team: list[str] = Field(min_length=4, max_length=4)
    strategy_ru: str = Field(min_length=20, max_length=1_500)
    synergies_ru: list[str] = Field(min_length=1, max_length=8)
    weak_points_ru: list[str] = Field(default_factory=list, max_length=8)
    rubric: TeamRubricEvidence


class TeamScoreBreakdown(BaseModel):
    raw_scores: dict[TeamMetric, int]
    weighted_points: dict[TeamMetric, float]
    total: float = Field(ge=0, le=100)


class TeamCandidateEvaluation(BaseModel):
    proposal_id: str
    team: list[str]
    score: float = Field(ge=0, le=100)
    accepted: bool
    rejection_reasons_ru: list[str]
    breakdown: TeamScoreBreakdown
    evidence_ru: list[str]


class TeamEvaluationReport(BaseModel):
    scope: TeamScope
    objective: TeamObjective
    acceptance_threshold: float
    selected_proposal_id: str | None
    gate_errors_ru: list[str]
    excluded_by_preference: list[str]
    candidates: list[TeamCandidateEvaluation]


class TeamEvaluationPair(BaseModel):
    evaluator: Literal["deterministic_rubric_v1"] = "deterministic_rubric_v1"
    exact_dps_claimed: Literal[False] = False
    target: TeamEvaluationReport
    domain: TeamEvaluationReport


class TeamEvaluationError(ValueError):
    def __init__(self, message: str, reports: list[TeamEvaluationReport]) -> None:
        super().__init__(message)
        self.reports = reports

    def feedback_ru(self) -> str:
        parts: list[str] = []
        for report in self.reports:
            scope = "целевая" if report.scope == "target" else "доменная"
            if report.gate_errors_ru:
                parts.append(f"{scope}: " + "; ".join(report.gate_errors_ru))
            for candidate in report.candidates:
                if not candidate.accepted:
                    parts.append(
                        f"{scope}/{candidate.proposal_id}: "
                        + "; ".join(candidate.rejection_reasons_ru)
                    )
        return " | ".join(parts)[:4_000]


_WEIGHTS: dict[TeamObjective, dict[TeamMetric, int]] = {
    "max_dps": {
        "damage_potential": 35,
        "reaction_coherence": 20,
        "rotation_stability": 15,
        "energy_feasibility": 10,
        "comfort": 5,
        "account_readiness": 15,
        "domain_compatibility": 0,
    },
    "comfort": {
        "damage_potential": 10,
        "reaction_coherence": 10,
        "rotation_stability": 20,
        "energy_feasibility": 15,
        "comfort": 30,
        "account_readiness": 15,
        "domain_compatibility": 0,
    },
    "stable_rotation": {
        "damage_potential": 20,
        "reaction_coherence": 15,
        "rotation_stability": 25,
        "energy_feasibility": 20,
        "comfort": 10,
        "account_readiness": 10,
        "domain_compatibility": 0,
    },
}

_DOMAIN_WEIGHTS: dict[TeamObjective, dict[TeamMetric, int]] = {
    "max_dps": {
        "damage_potential": 30,
        "reaction_coherence": 15,
        "rotation_stability": 10,
        "energy_feasibility": 10,
        "comfort": 5,
        "account_readiness": 10,
        "domain_compatibility": 20,
    },
    "comfort": {
        "damage_potential": 10,
        "reaction_coherence": 10,
        "rotation_stability": 15,
        "energy_feasibility": 10,
        "comfort": 25,
        "account_readiness": 10,
        "domain_compatibility": 20,
    },
    "stable_rotation": {
        "damage_potential": 15,
        "reaction_coherence": 10,
        "rotation_stability": 20,
        "energy_feasibility": 15,
        "comfort": 10,
        "account_readiness": 10,
        "domain_compatibility": 20,
    },
}

_THRESHOLDS: dict[TeamObjective, float] = {
    "max_dps": 62.0,
    "comfort": 64.0,
    "stable_rotation": 66.0,
}

_EXCLUSION_MARKERS = (
    "не использовать",
    "не брать",
    "исключить",
    "без",
)


def excluded_character_keys(preferences: str) -> set[str]:
    """Extract only explicit, nearby character exclusions; ambiguous prose is untouched."""

    text = preferences.casefold().replace("ё", "е")
    segments: list[tuple[str, str]] = []
    for marker in _EXCLUSION_MARKERS:
        for position in _marker_positions(text, marker):
            segment = text[position + len(marker) : position + len(marker) + 120]
            boundaries = [
                boundary
                for separator in (".", ";", "\n", " но ", " однако ", " зато ")
                if (boundary := segment.find(separator)) >= 0
            ]
            segments.append((marker, segment[: min(boundaries)] if boundaries else segment))
    excluded: set[str] = set()
    for key, character in CHARACTERS.items():
        aliases = {key.casefold(), character.name_ru.casefold().replace("ё", "е")}
        aliases |= {alias[:-1] for alias in aliases if len(alias) >= 6}
        if any(
            alias and _alias_is_excluded(marker, segment, alias)
            for alias in aliases
            for marker, segment in segments
        ):
            excluded.add(key)
    return excluded


def _marker_positions(text: str, marker: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        position = text.find(marker, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + len(marker)


def _alias_is_excluded(marker: str, segment: str, alias: str) -> bool:
    position = segment.find(alias)
    if position < 0:
        return False
    if marker != "без":
        return True
    prefix = segment[:position]
    return position <= 32 and "использ" not in prefix and "проблем" not in prefix


class TeamEvaluator:
    """Deterministically gates and ranks researched team candidates."""

    def evaluate_pair(
        self,
        *,
        target_candidates: list[TeamCandidateProposal],
        domain_candidates: list[TeamCandidateProposal],
        intent: TeamIntent,
        observed_keys: set[str],
        preferences: str,
    ) -> tuple[TeamCandidateProposal, TeamCandidateProposal, TeamEvaluationPair]:
        excluded = excluded_character_keys(preferences)
        target, selected_target = self.evaluate(
            candidates=target_candidates,
            scope="target",
            objective=intent.target_objective,
            intent=intent,
            observed_keys=observed_keys,
            excluded=excluded,
        )
        domain, selected_domain = self.evaluate(
            candidates=domain_candidates,
            scope="domain",
            objective=intent.domain_objective,
            intent=intent,
            observed_keys=observed_keys,
            excluded=excluded,
            selected_target_team=(selected_target.team if selected_target else None),
        )
        failed = [report for report in (target, domain) if report.selected_proposal_id is None]
        if failed or selected_target is None or selected_domain is None:
            raise TeamEvaluationError("Не удалось подобрать две подходящие команды", failed)
        return selected_target, selected_domain, TeamEvaluationPair(
            target=target,
            domain=domain,
        )

    def evaluate(
        self,
        *,
        candidates: list[TeamCandidateProposal],
        scope: TeamScope,
        objective: TeamObjective,
        intent: TeamIntent,
        observed_keys: set[str],
        excluded: set[str],
        selected_target_team: list[str] | None = None,
    ) -> tuple[TeamEvaluationReport, TeamCandidateProposal | None]:
        threshold = _THRESHOLDS[objective]
        allowed, exact = self._boundaries(scope, intent, selected_target_team)
        gate_errors: list[str] = []
        if self._needs_alternatives(scope, intent, allowed) and len(candidates) < 2:
            gate_errors.append("Для автоподбора нужны минимум два разных состава")

        evaluations: list[TeamCandidateEvaluation] = []
        accepted: list[tuple[float, int, TeamCandidateProposal]] = []
        seen: set[frozenset[str]] = set()
        for index, proposal in enumerate(candidates):
            reasons: list[str] = []
            team_set = set(proposal.team)
            signature = frozenset(proposal.team)
            if len(proposal.team) != 4 or len(team_set) != 4:
                reasons.append("состав должен содержать четырёх разных персонажей")
            if signature in seen:
                reasons.append("Этот состав уже встречался среди вариантов")
            seen.add(signature)
            outside_allowed = sorted(team_set - allowed)
            if outside_allowed:
                reasons.append("Эти персонажи не были выбраны для подбора: " + ", ".join(outside_allowed))
            outside_observed = sorted(team_set - observed_keys)
            if outside_observed:
                reasons.append("Этих персонажей нет в загруженных витринах Enka: " + ", ".join(outside_observed))
            if scope == "target" and intent.target_key not in team_set:
                reasons.append("Основная команда не содержит выбранного персонажа")
            if exact is not None and team_set != exact:
                reasons.append("Вариант не совпадает с указанным вами составом")
            excluded_present = sorted(team_set & excluded)
            if excluded_present:
                reasons.append(
                    "В состав добавлен исключённый вами персонаж: "
                    + ", ".join(CHARACTERS[key].name_ru for key in excluded_present)
                )
            reasons.extend(self._rubric_rejections(proposal.rubric, objective, scope, threshold))
            breakdown = self._score(proposal.rubric, objective, scope)
            accepted_candidate = not reasons and not gate_errors
            evaluations.append(
                TeamCandidateEvaluation(
                    proposal_id=proposal.proposal_id,
                    team=proposal.team,
                    score=breakdown.total,
                    accepted=accepted_candidate,
                    rejection_reasons_ru=reasons,
                    breakdown=breakdown,
                    evidence_ru=proposal.rubric.evidence_ru,
                )
            )
            if accepted_candidate:
                accepted.append((breakdown.total, -index, proposal))

        selected = max(accepted, default=None, key=lambda item: (item[0], item[1]))
        selected_proposal = selected[2] if selected else None
        report = TeamEvaluationReport(
            scope=scope,
            objective=objective,
            acceptance_threshold=threshold,
            selected_proposal_id=(selected_proposal.proposal_id if selected_proposal else None),
            gate_errors_ru=gate_errors,
            excluded_by_preference=sorted(excluded),
            candidates=evaluations,
        )
        return report, selected_proposal

    @staticmethod
    def _boundaries(
        scope: TeamScope,
        intent: TeamIntent,
        selected_target_team: list[str] | None,
    ) -> tuple[set[str], set[str] | None]:
        pool = set(intent.candidate_pool) | {intent.target_key}
        if scope == "target":
            if intent.target_team_mode == "manual":
                exact = set(intent.target_team)
                return exact, exact
            return pool, None
        if intent.domain_team_mode == "same":
            exact = set(selected_target_team or [])
            return exact, exact
        if intent.domain_team_mode == "manual":
            exact = set(intent.domain_team)
            return exact, exact
        return pool, None

    @staticmethod
    def _needs_alternatives(scope: TeamScope, intent: TeamIntent, allowed: set[str]) -> bool:
        auto = intent.target_team_mode == "auto" if scope == "target" else intent.domain_team_mode == "auto"
        if not auto:
            return False
        if scope == "target":
            return len(allowed - {intent.target_key}) > 3
        return len(allowed) > 4

    @staticmethod
    def _rubric_rejections(
        rubric: TeamRubricEvidence,
        objective: TeamObjective,
        scope: TeamScope,
        threshold: float,
    ) -> list[str]:
        reasons: list[str] = []
        if not rubric.mechanics_verified:
            reasons.append("Не хватает свежих источников по механикам всех четырёх персонажей")
        if rubric.reaction_coherence < 2:
            reasons.append("реакции или механики состава конфликтуют")
        if rubric.energy_feasibility < 2:
            reasons.append("Команде не хватает энергии для стабильной ротации")
        if scope == "domain" and rubric.domain_compatibility < 3:
            reasons.append("Состав плохо подходит выбранному домену")
        if objective == "max_dps" and rubric.damage_potential < 3:
            reasons.append("Урон ниже минимального порога для режима «Максимальный DPS»")
        if objective == "comfort" and rubric.comfort < 3:
            reasons.append("Для комфортной игры не хватает лечения, щита или устойчивости")
        if objective == "stable_rotation":
            if rubric.rotation_stability < 3:
                reasons.append("Ротацию сложно повторять без сбоев")
            if rubric.energy_feasibility < 3:
                reasons.append("энергия недостаточно стабильна для повторяемой ротации")
        score = TeamEvaluator._score(rubric, objective, scope).total
        if score < threshold:
            reasons.append(f"итоговая оценка {score:.1f} ниже порога {threshold:.1f}")
        return reasons

    @staticmethod
    def _score(
        rubric: TeamRubricEvidence,
        objective: TeamObjective,
        scope: TeamScope,
    ) -> TeamScoreBreakdown:
        weights = _DOMAIN_WEIGHTS[objective] if scope == "domain" else _WEIGHTS[objective]
        raw: dict[TeamMetric, int] = {
            metric: int(getattr(rubric, metric)) for metric in weights
        }
        points: dict[TeamMetric, float] = {
            metric: round(raw[metric] / 5 * weight, 1)
            for metric, weight in weights.items()
        }
        return TeamScoreBreakdown(
            raw_scores=raw,
            weighted_points=points,
            total=round(sum(points.values()), 1),
        )
