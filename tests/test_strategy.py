from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from grindless.character_catalog import TeamIntent
from grindless.enka import EnkaCharacterProfile
from grindless.llm import (
    AuditedLLM,
    LLMBackend,
    LLMCompletion,
    LLMRequest,
    SQLiteQuotaStore,
)
from grindless.strategy import StrategyOutputError, TeamStrategist
from grindless.team_evaluator import excluded_character_keys


class _StrategyProvider:
    backend = LLMBackend.OPENAI_LUNA
    model = "strategy-test-model"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        return LLMCompletion(
            text=json.dumps(self.payload, ensure_ascii=False),
            input_tokens=500,
            output_tokens=180,
            response_id="resp_strategy",
            web_search_used=request.web_search,
        )


class _SequenceStrategyProvider(_StrategyProvider):
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        return LLMCompletion(
            text=self.outputs[len(self.requests) - 1],
            input_tokens=500,
            output_tokens=180,
            response_id=f"resp_strategy_{len(self.requests)}",
            web_search_used=request.web_search,
        )


def profile(key: str) -> EnkaCharacterProfile:
    avatar_ids = {
        "Mavuika": 10000106,
        "Citlali": 10000107,
        "Xilonen": 10000103,
        "Bennett": 10000032,
        "Furina": 10000089,
        "Alyosha": 10000148,
    }
    return EnkaCharacterProfile(
        character_key=key,
        name_ru=key,
        avatar_id=avatar_ids[key],
        captured_at=datetime.now(UTC),
        character_level=90,
        constellation=0,
        skill_levels={"1": 8},
        weapon_id=1,
        weapon_level=90,
        weapon_refinement=1,
    )


def proposal(
    proposal_id: str,
    team: list[str],
    *,
    score: int = 4,
    mechanics_verified: bool = True,
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "team": team,
        "strategy_ru": "Команда создаёт проверяемое окно урона и повторяемый цикл способностей.",
        "synergies_ru": ["Баффы и реакции согласованы с ролью главного источника урона."],
        "weak_points_ru": ["Фактическую длительность цикла нужно проверить в теневом режиме."],
        "rubric": {
            "damage_potential": score,
            "reaction_coherence": score,
            "rotation_stability": score,
            "energy_feasibility": score,
            "comfort": score,
            "account_readiness": score,
            "domain_compatibility": score,
            "mechanics_verified": mechanics_verified,
            "evidence_ru": [
                "Актуальные описания навыков и командные роли проверены поиском.",
                "Источник подтверждает реакционную связку и повторяемость цикла.",
            ],
        },
    }


def draft(
    target_team: list[str],
    domain_team: list[str],
    *,
    confidence: str = "high",
    target_objective: str = "max_dps",
    domain_objective: str = "stable_rotation",
    target_alternatives: list[list[str]] | None = None,
    domain_alternatives: list[list[str]] | None = None,
) -> dict[str, object]:
    return {
        "target_objective": target_objective,
        "domain_objective": domain_objective,
        "target_candidates": [
            proposal(f"target_{index}", team)
            for index, team in enumerate([target_team, *(target_alternatives or [])], 1)
        ],
        "domain_candidates": [
            proposal(f"domain_{index}", team)
            for index, team in enumerate([domain_team, *(domain_alternatives or [])], 1)
        ],
        "recommendations_ru": ["Проверить ротацию в теневом режиме до управления игрой."],
        "preference_handling_ru": "Комментарий пользователя применён к выбору стабильного цикла.",
        "assumptions_ru": [],
        "confidence": confidence,
    }


class TeamStrategistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def strategist(self, payload: dict[str, object]) -> tuple[TeamStrategist, _StrategyProvider]:
        provider = _StrategyProvider(payload)
        llm = AuditedLLM(
            provider,
            SQLiteQuotaStore(Path(self.directory.name) / "state.sqlite3"),
        )
        return TeamStrategist(llm), provider

    def test_explicit_exclusion_parser_stops_at_contrast_clause(self) -> None:
        self.assertEqual(
            excluded_character_keys("Не использовать Беннета, но можно Фурину."),
            {"Bennett"},
        )
        self.assertEqual(
            excluded_character_keys("Без Беннета или Фурины."),
            {"Bennett", "Furina"},
        )
        self.assertEqual(
            excluded_character_keys("Можно без проблем использовать Фурину."),
            set(),
        )

    def test_manual_team_is_analyzed_but_cannot_be_changed(self) -> None:
        team = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        strategist, provider = self.strategist(draft(team, team))
        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="manual",
                target_team=team,
                domain_team_mode="same",
            ),
            [profile(key) for key in team],
            "Хочу стабильную ротацию",
        )

        self.assertEqual(result.target_team, team)
        self.assertEqual(result.domain_team, team)
        self.assertEqual(result.decision_owner, "llm_plus_team_evaluator")
        self.assertEqual(result.execution_status, "shadow_only")
        self.assertEqual(result.validation.knowledge_coverage, "curated")
        self.assertEqual(result.llm_audit.successful_calls, 1)
        self.assertEqual(len(provider.requests), 1)
        self.assertIn("Хочу стабильную ротацию", provider.requests[0].input_text)
        self.assertNotIn("700123456", result.llm_audit.calls[0].transmitted_text)

    def test_auto_team_is_restricted_to_the_explicit_pool(self) -> None:
        target = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        domain = list(target)
        strategist, _ = self.strategist(draft(target, domain, confidence="medium"))
        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="auto",
                domain_team_mode="auto",
                candidate_pool=["Citlali", "Xilonen", "Bennett"],
            ),
            [profile(key) for key in domain],
        )

        self.assertEqual(result.validated_team_plan.target_team_status, "confirmed")
        self.assertEqual(result.target_team, target)
        self.assertEqual(result.domain_team, domain)

    def test_auto_domain_team_is_independent_and_may_exclude_target(self) -> None:
        target = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        domain = ["Citlali", "Xilonen", "Bennett", "Furina"]
        pool = ["Citlali", "Xilonen", "Bennett", "Furina"]
        strategist, _ = self.strategist(
            draft(
                target,
                domain,
                target_alternatives=[["Mavuika", "Citlali", "Xilonen", "Furina"]],
                domain_alternatives=[["Mavuika", "Citlali", "Xilonen", "Bennett"]],
            )
        )

        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="auto",
                domain_team_mode="auto",
                candidate_pool=pool,
            ),
            [profile(key) for key in ["Mavuika", *pool]],
        )

        self.assertNotIn("Mavuika", result.domain_team)
        self.assertEqual(result.evaluation.evaluator, "deterministic_rubric_v1")
        self.assertFalse(result.evaluation.exact_dps_claimed)
        self.assertIn(
            "команда домена подобрана независимо от основного состава",
            result.validation.checks,
        )

    def test_user_objectives_are_transmitted_and_cannot_be_changed(self) -> None:
        team = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        intent = TeamIntent(
            target_key="Mavuika",
            target_objective="comfort",
            target_team_mode="manual",
            target_team=team,
            domain_team_mode="same",
            domain_objective="stable_rotation",
        )
        strategist, provider = self.strategist(
            draft(
                team,
                team,
                target_objective="comfort",
                domain_objective="stable_rotation",
            )
        )
        result = strategist.plan(intent, [profile(key) for key in team])

        self.assertEqual(result.validated_team_plan.target_objective, "comfort")
        self.assertEqual(result.validated_team_plan.domain_objective, "stable_rotation")
        self.assertIn("Комфорт", provider.requests[0].input_text)
        self.assertIn("Стабильный DPS и ротация", provider.requests[0].input_text)

        invalid, _ = self.strategist(draft(team, team))
        with self.assertRaisesRegex(StrategyOutputError, "выбранная цель основной команды"):
            invalid.plan(intent, [profile(key) for key in team])

    def test_model_cannot_replace_a_manual_character(self) -> None:
        manual = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        changed = ["Mavuika", "Furina", "Xilonen", "Bennett"]
        strategist, _ = self.strategist(draft(changed, changed))

        with self.assertRaisesRegex(StrategyOutputError, "не совпадает с указанным вами составом"):
            strategist.plan(
                TeamIntent(
                    target_key="Mavuika",
                    target_team_mode="manual",
                    target_team=manual,
                    domain_team_mode="same",
                ),
                [profile(key) for key in {*manual, "Furina"}],
            )

    def test_evaluator_selects_the_best_accepted_candidate(self) -> None:
        first = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        better = ["Mavuika", "Citlali", "Xilonen", "Furina"]
        domain = ["Citlali", "Xilonen", "Bennett", "Furina"]
        payload = draft(
            first,
            domain,
            target_alternatives=[better],
            domain_alternatives=[first],
        )
        payload["target_candidates"][0] = proposal("target_low", first, score=3)
        payload["target_candidates"][1] = proposal("target_best", better, score=5)
        strategist, _ = self.strategist(payload)

        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="auto",
                domain_team_mode="auto",
                candidate_pool=["Citlali", "Xilonen", "Bennett", "Furina"],
            ),
            [profile(key) for key in ["Mavuika", "Citlali", "Xilonen", "Bennett", "Furina"]],
        )

        self.assertEqual(result.target_team, better)
        self.assertEqual(result.evaluation.target.selected_proposal_id, "target_best")
        self.assertGreater(
            result.evaluation.target.candidates[1].score,
            result.evaluation.target.candidates[0].score,
        )

    def test_explicit_character_exclusion_is_a_hard_gate(self) -> None:
        forbidden = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        allowed = ["Mavuika", "Citlali", "Xilonen", "Furina"]
        payload = draft(
            forbidden,
            allowed,
            target_alternatives=[allowed],
            domain_alternatives=[["Citlali", "Xilonen", "Bennett", "Furina"]],
        )
        strategist, _ = self.strategist(payload)

        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="auto",
                domain_team_mode="auto",
                candidate_pool=["Citlali", "Xilonen", "Bennett", "Furina"],
            ),
            [profile(key) for key in ["Mavuika", "Citlali", "Xilonen", "Bennett", "Furina"]],
            "Не использовать Беннета ни в одной команде.",
        )

        self.assertNotIn("Bennett", result.target_team)
        self.assertNotIn("Bennett", result.domain_team)
        rejected = result.evaluation.target.candidates[0]
        self.assertFalse(rejected.accepted)
        self.assertIn("Беннет", rejected.rejection_reasons_ru[0])

    def test_evaluator_retries_once_after_weak_candidates(self) -> None:
        team = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        weak = draft(team, team)
        weak["target_candidates"][0] = proposal("weak_target", team, score=1)
        strong = draft(team, team)
        provider = _SequenceStrategyProvider(
            [json.dumps(weak, ensure_ascii=False), json.dumps(strong, ensure_ascii=False)]
        )
        strategist = TeamStrategist(
            AuditedLLM(
                provider,
                SQLiteQuotaStore(Path(self.directory.name) / "quality-retry.sqlite3"),
            )
        )

        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="manual",
                target_team=team,
                domain_team_mode="same",
            ),
            [profile(key) for key in team],
        )

        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(provider.requests[1].purpose, "account_and_team_strategy_quality_retry")
        self.assertIn("итоговая оценка", provider.requests[1].input_text)
        self.assertEqual(result.llm_audit.calls[0].status, "invalid_output")

    def test_web_research_can_cover_identity_only_local_role(self) -> None:
        team = ["Mavuika", "Alyosha", "Xilonen", "Bennett"]
        strategist, _ = self.strategist(draft(team, team))
        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="manual",
                target_team=team,
                domain_team_mode="same",
            ),
            [profile(key) for key in team],
        )

        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.validation.knowledge_coverage, "web_researched")

    def test_truncated_json_is_retried_once_with_a_larger_budget(self) -> None:
        team = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        provider = _SequenceStrategyProvider(
            [
                '{"target_team":["Mavuika',
                json.dumps(draft(team, team), ensure_ascii=False),
            ]
        )
        strategist = TeamStrategist(
            AuditedLLM(
                provider,
                SQLiteQuotaStore(Path(self.directory.name) / "retry.sqlite3"),
            )
        )

        result = strategist.plan(
            TeamIntent(
                target_key="Mavuika",
                target_team_mode="manual",
                target_team=team,
                domain_team_mode="same",
            ),
            [profile(key) for key in team],
        )

        self.assertEqual(result.target_team, team)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(provider.requests[0].max_output_tokens, 6_000)
        self.assertEqual(provider.requests[1].max_output_tokens, 8_000)
        self.assertIsNotNone(provider.requests[0].response_schema)
        self.assertEqual(result.llm_audit.calls[0].status, "invalid_output")
        self.assertEqual(result.llm_audit.calls[1].status, "succeeded")
        self.assertEqual(result.llm_audit.successful_calls, 1)
        self.assertEqual(result.llm_audit.failed_calls, 1)


if __name__ == "__main__":
    unittest.main()
