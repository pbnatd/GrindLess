from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from grindless.artifact_strategy import ArtifactGoalOutputError, ArtifactGoalPlanner
from grindless.character_catalog import CHARACTERS, TeamIntent
from grindless.enka import EnkaCharacterProfile
from grindless.llm import AuditedLLM, LLMBackend, LLMCompletion, LLMRequest, SQLiteQuotaStore


class _Provider:
    backend = LLMBackend.OPENAI_LUNA
    model = "artifact-goal-test"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        return LLMCompletion(
            text=self.outputs[len(self.requests) - 1],
            input_tokens=700,
            output_tokens=240,
            response_id=f"resp_artifact_{len(self.requests)}",
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


def _good() -> dict[str, object]:
    slots = [
        ("flower", "hp"),
        ("plume", "atk"),
        ("sands", "eleMas"),
        ("goblet", "pyro_dmg_"),
        ("circlet", "critRate_"),
    ]
    return {
        "format": "GOOD",
        "version": 3,
        "source": "artifact strategy test",
        "characters": [
            {
                "key": "Mavuika",
                "level": 90,
                "constellation": 1,
                "ascension": 6,
                "talent": {"auto": 8, "skill": 9, "burst": 8},
            }
        ],
        "weapons": [
            {
                "key": "AThousandBlazingSuns",
                "level": 90,
                "ascension": 6,
                "refinement": 1,
                "location": "Mavuika",
            }
        ],
        "artifacts": [
            {
                "setKey": "ObsidianCodex",
                "slotKey": slot,
                "level": 0,
                "rarity": 5,
                "mainStatKey": main,
                "substats": [
                    {"key": "critDMG_", "value": 7.8},
                    {"key": "enerRech_", "value": 5.2},
                ],
            }
            for slot, main in slots
        ],
    }


def _nilou_good() -> dict[str, object]:
    items = [
        ("TenacityOfTheMillelith", "flower", "hp"),
        ("TenacityOfTheMillelith", "plume", "atk"),
        ("VourukashasGlow", "sands", "hp_"),
        ("VourukashasGlow", "goblet", "hp_"),
        ("OceanHuedClam", "circlet", "hp_"),
    ]
    return {
        "format": "GOOD",
        "version": 3,
        "source": "mixed set strategy test",
        "artifacts": [
            {
                "setKey": set_name,
                "slotKey": slot,
                "level": 0,
                "rarity": 5,
                "mainStatKey": main,
                "substats": (
                    [
                        {"key": "eleMas", "value": 23},
                        {"key": "enerRech_", "value": 5.2},
                    ]
                    if main == "hp_"
                    else [
                        {"key": "hp_", "value": 5.8},
                        {"key": "eleMas", "value": 23},
                    ]
                ),
            }
            for set_name, slot, main in items
        ],
    }


def _draft(*, selected_set_option_id: str = "primary_4pc") -> dict[str, object]:
    return {
        "build_role_ru": "Мавуика наносит основной урон в стабильной команде домена.",
        "selected_set_option_id": selected_set_option_id,
        "slots": [
            {
                "slot": "flower",
                "allowed_main_stats": ["hp_flat"],
                "min_useful_substats": 2,
                "rationale_ru": "Основная характеристика цветка фиксирована правилами игры.",
            },
            {
                "slot": "plume",
                "allowed_main_stats": ["atk_flat"],
                "min_useful_substats": 2,
                "rationale_ru": "Основная характеристика пера фиксирована правилами игры.",
            },
            {
                "slot": "sands",
                "allowed_main_stats": ["elemental_mastery", "atk_pct"],
                "min_useful_substats": 2,
                "rationale_ru": "Мастерство важно для реакций, а атака остаётся запасным вариантом.",
            },
            {
                "slot": "goblet",
                "allowed_main_stats": ["pyro_dmg", "atk_pct"],
                "min_useful_substats": 2,
                "rationale_ru": "Пиро-урон предпочтителен, атака допустима как временная база.",
            },
            {
                "slot": "circlet",
                "allowed_main_stats": ["crit_rate", "crit_dmg"],
                "min_useful_substats": 2,
                "rationale_ru": "Крит выбирается с учётом уже наблюдаемого баланса характеристик.",
            },
        ],
        "substat_priority_order": [
            "crit_rate",
            "crit_dmg",
            "elemental_mastery",
            "atk_pct",
            "energy_recharge",
        ],
        "slot_priority_order": ["goblet", "circlet", "sands", "plume", "flower"],
        "farming_plan_ru": "Сначала закрыть кубок и корону, затем улучшать часы по текущему балансу.",
        "alternative_upgrade_ru": "После проверки ротации сравнить фарм с гарантированной прокачкой талантов.",
        "preference_handling_ru": "Комментарий пользователя применён к порядку улучшения сборки.",
        "assumptions_ru": ["Точный порог восстановления энергии ждёт проверки ротации."],
        "confidence": "medium",
    }


def _nilou_draft() -> dict[str, object]:
    draft = _draft(selected_set_option_id="double_hp_2pc")
    draft["build_role_ru"] = "Нилу усиливает Bloom через запас HP в подтверждённой команде."
    draft["slots"][2]["allowed_main_stats"] = ["hp_pct"]
    draft["slots"][3]["allowed_main_stats"] = ["hp_pct"]
    draft["slots"][4]["allowed_main_stats"] = ["hp_pct"]
    draft["substat_priority_order"] = [
        "hp_pct",
        "elemental_mastery",
        "energy_recharge",
    ]
    return draft


class ArtifactGoalPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _planner(self, outputs: list[str]) -> tuple[ArtifactGoalPlanner, _Provider]:
        provider = _Provider(outputs)
        planner = ArtifactGoalPlanner(
            AuditedLLM(
                provider,
                SQLiteQuotaStore(Path(self.directory.name) / "state.sqlite3"),
            )
        )
        return planner, provider

    def test_model_goal_is_validated_and_reaudits_good_locally(self) -> None:
        planner, provider = self._planner([json.dumps(_draft(), ensure_ascii=False)])

        result = planner.plan(_good(), _intent(), _profiles())

        self.assertEqual(result.decision_owner, "llm")
        self.assertEqual(result.execution_status, "shadow_only")
        self.assertEqual(
            result.resolved_goal.constraints.set_requirements[0].set_name,
            "ObsidianCodex",
        )
        self.assertEqual(result.resolved_goal.constraints.set_requirements[0].pieces, 4)
        self.assertEqual(len(result.resolved_goal.targets), 5)
        self.assertTrue(result.inventory_audit.starter_build_available)
        self.assertEqual(result.evidence.target.weapon_key, "AThousandBlazingSuns")
        self.assertEqual(result.llm_audit.successful_calls, 1)
        self.assertIn("candidate_observations", provider.requests[0].input_text)
        self.assertNotIn('"format": "GOOD"', provider.requests[0].input_text)

    def test_unknown_set_fails_loudly(self) -> None:
        planner, _ = self._planner(
            [json.dumps(_draft(selected_set_option_id="invented_set"), ensure_ascii=False)]
        )

        with self.assertRaisesRegex(ArtifactGoalOutputError, "outside the curated"):
            planner.plan(_good(), _intent(), _profiles())

    def test_mixed_profile_builds_two_plus_two_with_an_exact_off_piece(self) -> None:
        planner, _ = self._planner([json.dumps(_nilou_draft(), ensure_ascii=False)])
        keys = ["Nilou", "Nahida", "Xingqiu", "KukiShinobu"]
        profiles = [_profile(key, CHARACTERS[key].avatar_id) for key in keys]
        intent = TeamIntent(
            target_key="Nilou",
            target_team_mode="manual",
            target_team=keys,
            domain_team_mode="same",
        )

        result = planner.plan(_nilou_good(), intent, profiles)

        self.assertEqual(
            {(item.set_name, item.pieces) for item in result.resolved_goal.constraints.set_requirements},
            {
                ("TenacityOfTheMillelith", 2),
                ("VourukashasGlow", 2),
            },
        )
        self.assertTrue(result.inventory_audit.set_composition_met)
        self.assertIsNotNone(result.inventory_audit.off_piece_artifact_id)
        self.assertEqual(result.validation.off_piece_status, "optimized_locally")

    def test_main_stat_outside_character_profile_fails_loudly(self) -> None:
        draft = _draft()
        draft["slots"][2]["allowed_main_stats"] = ["hp_pct"]
        planner, _ = self._planner([json.dumps(draft, ensure_ascii=False)])

        with self.assertRaisesRegex(ArtifactGoalOutputError, "outside the curated profile"):
            planner.plan(_good(), _intent(), _profiles())

    def test_truncated_goal_is_retried_once(self) -> None:
        planner, provider = self._planner(
            ['{"build_role_ru":"оборвано', json.dumps(_draft(), ensure_ascii=False)]
        )

        result = planner.plan(_good(), _intent(), _profiles())

        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(provider.requests[0].purpose, "artifact_goal_strategy")
        self.assertEqual(provider.requests[1].purpose, "artifact_goal_strategy_recovery")
        self.assertEqual(result.llm_audit.failed_calls, 1)
        self.assertEqual(result.llm_audit.successful_calls, 1)

    def test_auto_team_must_be_resolved_before_artifact_planning(self) -> None:
        planner, provider = self._planner([json.dumps(_draft(), ensure_ascii=False)])
        intent = TeamIntent(
            target_key="Mavuika",
            target_team_mode="auto",
            domain_team_mode="same",
            candidate_pool=["Citlali", "Xilonen", "Bennett"],
        )

        with self.assertRaisesRegex(ValueError, "confirmed teams"):
            planner.plan(_good(), intent, _profiles())
        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
