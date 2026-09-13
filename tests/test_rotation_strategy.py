from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from grindless.character_catalog import TeamIntent, build_team_plan
from grindless.enka import EnkaCharacterProfile
from grindless.llm import (
    AuditedLLM,
    LLMBackend,
    LLMCompletion,
    LLMRequest,
    SQLiteQuotaStore,
)
from grindless.rotation_strategy import (
    RotationOutputError,
    RotationPlanner,
    validate_resolved_rotation,
)


class _Provider:
    backend = LLMBackend.OPENAI_LUNA
    model = "rotation-test"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        return LLMCompletion(
            text=self.outputs[len(self.requests) - 1],
            input_tokens=500,
            output_tokens=210,
            response_id=f"resp_rotation_{len(self.requests)}",
            web_search_used=request.web_search,
        )


def _profile(key: str, avatar_id: int) -> EnkaCharacterProfile:
    return EnkaCharacterProfile(
        character_key=key,
        name_ru=key,
        avatar_id=avatar_id,
        captured_at=datetime.now(UTC),
        character_level=90,
        constellation=1,
        skill_levels={"1": 8, "2": 9, "3": 8},
        weapon_id=123,
        weapon_level=90,
        weapon_refinement=1,
    )


def _profiles() -> list[EnkaCharacterProfile]:
    return [
        _profile("Mavuika", 10000106),
        _profile("Citlali", 10000107),
        _profile("Xilonen", 10000103),
        _profile("Bennett", 10000032),
    ]


def _intent() -> TeamIntent:
    return TeamIntent(
        target_key="Mavuika",
        target_team_mode="manual",
        target_team=["Mavuika", "Citlali", "Xilonen", "Bennett"],
        domain_team_mode="same",
    )


def _draft() -> dict[str, object]:
    return {
        "domain_team": ["Mavuika", "Citlali", "Xilonen", "Bennett"],
        "opening_ru": "Начать с подготовки защиты и командных усилений до окна Мавуики.",
        "steps": [
            {
                "character_key": "Citlali",
                "action": "skill",
                "repetitions": 1,
                "purpose_ru": "Создать защитный слой перед основным окном урона.",
            },
            {
                "character_key": "Xilonen",
                "action": "skill",
                "repetitions": 1,
                "purpose_ru": "Подготовить поддержку команды перед главным персонажем.",
            },
            {
                "character_key": "Bennett",
                "action": "burst",
                "repetitions": 1,
                "purpose_ru": "Открыть командное окно усиления и восстановления.",
            },
            {
                "character_key": "Mavuika",
                "action": "skill",
                "repetitions": 1,
                "purpose_ru": "Активировать состояние главного источника урона.",
            },
            {
                "character_key": "Mavuika",
                "action": "burst",
                "repetitions": 1,
                "purpose_ru": "Использовать главное окно урона после подготовки команды.",
            },
            {
                "character_key": "Mavuika",
                "action": "normal_attack",
                "repetitions": 4,
                "purpose_ru": "Продолжить основное окно до нового цикла поддержки.",
            },
        ],
        "burst_fallbacks": [
            {
                "at_step": 3,
                "response": "use_skill_then_retry",
                "rationale_ru": "Навык создаёт безопасную попытку восстановить цикл перед ультой.",
            },
            {
                "at_step": 5,
                "response": "restart_rotation",
                "rationale_ru": "Без главной способности лучше вернуться к подготовке команды.",
            },
        ],
        "repeat_from_step": 1,
        "stop_conditions_ru": [
            "Остановиться, если действие не подтверждено наблюдением игры."
        ],
        "preference_handling_ru": "Комментарий пользователя применён к безопасному циклу ротации.",
        "assumptions_ru": [
            "Точный порог энергии и длительность окна пока не рассчитаны."
        ],
        "rationale_ru": "Порядок сначала создаёт защиту и усиления, затем открывает окно Мавуики.",
        "confidence": "high",
    }


class RotationPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _planner(self, outputs: list[str]) -> tuple[RotationPlanner, _Provider]:
        provider = _Provider(outputs)
        planner = RotationPlanner(
            AuditedLLM(
                provider,
                SQLiteQuotaStore(Path(self.directory.name) / "state.sqlite3"),
            )
        )
        return planner, provider

    def test_model_rotation_is_compiled_without_input_authority(self) -> None:
        planner, provider = self._planner([json.dumps(_draft(), ensure_ascii=False)])

        result = planner.plan(_intent(), _profiles())

        self.assertEqual(result.decision_owner, "llm")
        self.assertEqual(result.execution_status, "shadow_only")
        self.assertEqual(result.validation.timing_status, "web_researched")
        self.assertEqual(result.validated_rotation.input_authority, "none")
        self.assertEqual(result.draft.confidence, "high")
        self.assertEqual(len(result.validated_rotation.plan_fingerprint), 64)
        recovery = next(
            state
            for state in result.validated_rotation.states
            if state.state_id == "recovery_03_skill"
        )
        self.assertTrue(recovery.recovery)
        self.assertEqual(recovery.on_success, "step_03")
        self.assertEqual(provider.requests[0].purpose, "rotation_strategy")
        self.assertNotIn('"format":"GOOD"', provider.requests[0].input_text)

    def test_character_outside_team_fails_loudly(self) -> None:
        draft = _draft()
        draft["steps"][0]["character_key"] = "Furina"
        planner, _ = self._planner([json.dumps(draft, ensure_ascii=False)])

        with self.assertRaisesRegex(RotationOutputError, "outside the team"):
            planner.plan(_intent(), _profiles())

    def test_every_burst_requires_fallback(self) -> None:
        draft = _draft()
        draft["burst_fallbacks"] = draft["burst_fallbacks"][:1]
        planner, _ = self._planner([json.dumps(draft, ensure_ascii=False)])

        with self.assertRaisesRegex(RotationOutputError, "missing steps: 5"):
            planner.plan(_intent(), _profiles())

    def test_truncated_rotation_is_retried_once(self) -> None:
        planner, provider = self._planner(
            ['{"domain_team":["Mavuika"', json.dumps(_draft(), ensure_ascii=False)]
        )

        result = planner.plan(_intent(), _profiles())

        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(provider.requests[1].purpose, "rotation_strategy_recovery")
        self.assertEqual(result.llm_audit.failed_calls, 1)
        self.assertEqual(result.llm_audit.successful_calls, 1)

    def test_compiled_rotation_rejects_invalid_client_transition(self) -> None:
        planner, _ = self._planner([json.dumps(_draft(), ensure_ascii=False)])
        result = planner.plan(_intent(), _profiles())
        tampered = result.validated_rotation.model_copy(deep=True)
        tampered.states[0].on_success = "safe_stop"

        with self.assertRaisesRegex(ValueError, "success transitions"):
            validate_resolved_rotation(tampered, build_team_plan(_intent()))

    def test_compiled_rotation_fingerprint_covers_explanation(self) -> None:
        planner, _ = self._planner([json.dumps(_draft(), ensure_ascii=False)])
        result = planner.plan(_intent(), _profiles())
        tampered = result.validated_rotation.model_copy(deep=True)
        tampered.rationale_ru = "Подменённое объяснение, которое не принадлежит исходному плану."

        with self.assertRaisesRegex(ValueError, "fingerprint"):
            validate_resolved_rotation(tampered, build_team_plan(_intent()))

    def test_auto_team_must_be_resolved_before_rotation_planning(self) -> None:
        planner, provider = self._planner([json.dumps(_draft(), ensure_ascii=False)])
        intent = TeamIntent(
            target_key="Mavuika",
            target_team_mode="auto",
            domain_team_mode="same",
            candidate_pool=["Citlali", "Xilonen", "Bennett"],
        )

        with self.assertRaisesRegex(ValueError, "confirmed teams"):
            planner.plan(intent, _profiles())
        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
