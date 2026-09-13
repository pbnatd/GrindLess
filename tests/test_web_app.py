from __future__ import annotations

import tempfile
import unittest
import json
from asyncio import sleep
from pathlib import Path
from unittest.mock import patch

try:
    import httpx

    APP_TEST_DEPS_AVAILABLE = True
except ImportError:
    APP_TEST_DEPS_AVAILABLE = False

from grindless.video_import import VideoImportService
from grindless.web_app import create_app, server_port_from_environment
from grindless.enka import EnkaClient
from grindless.llm import AuditedLLM, LLMBackend, LLMCompletion, SQLiteQuotaStore
from grindless.strategy import TeamStrategist
from grindless.artifact_strategy import ArtifactGoalPlanner
from grindless.rotation_strategy import RotationPlanner


class ServerPortConfigurationTests(unittest.TestCase):
    def test_server_port_defaults_to_8765(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(server_port_from_environment(), 8765)

    def test_server_port_accepts_launcher_selected_port(self) -> None:
        with patch.dict("os.environ", {"GRINDLESS_PORT": "49152"}, clear=True):
            self.assertEqual(server_port_from_environment(), 49152)

    def test_server_port_rejects_invalid_values(self) -> None:
        for value in ("not-a-port", "0", "65536"):
            with self.subTest(value=value), patch.dict(
                "os.environ", {"GRINDLESS_PORT": value}, clear=True
            ):
                with self.assertRaises(ValueError):
                    server_port_from_environment()


class _VideoExtractor:
    last_audit = None

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.seen_path: Path | None = None

    def extract_good(self, video_path: Path) -> dict[str, object]:
        self.seen_path = video_path
        if not video_path.is_file():
            raise RuntimeError("test upload disappeared before extraction")
        return self.payload


class _StrategyProvider:
    backend = LLMBackend.OPENAI_LUNA
    model = "web-strategy-test"

    def complete(self, request):
        team = ["Mavuika", "Citlali", "Xilonen", "Bennett"]
        candidate = {
            "team": team,
            "strategy_ru": "Мавуика получает поддержку урона и устойчивое окно основной атаки.",
            "synergies_ru": ["Баффы команды поддерживают роль Мавуики как главного DPS."],
            "weak_points_ru": ["Ротацию ещё нужно проверить в теневом режиме."],
            "rubric": {
                "damage_potential": 4,
                "reaction_coherence": 4,
                "rotation_stability": 4,
                "energy_feasibility": 4,
                "comfort": 4,
                "account_readiness": 4,
                "domain_compatibility": 4,
                "mechanics_verified": True,
                "evidence_ru": [
                    "Актуальные навыки персонажей проверены поиском.",
                    "Реакционная связка и энергетический цикл подтверждены источниками.",
                ],
            },
        }
        return LLMCompletion(
            text=json.dumps({
                "target_objective": "max_dps",
                "domain_objective": "stable_rotation",
                "target_candidates": [{"proposal_id": "target_1", **candidate}],
                "domain_candidates": [{
                    "proposal_id": "domain_1",
                    **candidate,
                    "strategy_ru": "Этот же состав сохраняет лечение и защиту для стабильного домена.",
                }],
                "recommendations_ru": ["Не подключать ввод до валидации ротации."],
                "preference_handling_ru": "Комментарий пользователя применён к стабильности команды.",
                "assumptions_ru": [],
                "confidence": "high",
            }, ensure_ascii=False),
            input_tokens=400,
            output_tokens=160,
            response_id="resp_web_strategy",
            web_search_used=True,
        )


class _ArtifactProvider:
    backend = LLMBackend.OPENAI_LUNA
    model = "web-artifact-test"

    def complete(self, request):
        return LLMCompletion(
            text=json.dumps({
                "build_role_ru": "Мавуика наносит основной урон в подтверждённой команде домена.",
                "selected_set_option_id": "primary_4pc",
                "slots": [
                    {"slot": "flower", "allowed_main_stats": ["hp_flat"], "min_useful_substats": 2, "rationale_ru": "Основная характеристика цветка фиксирована правилами игры."},
                    {"slot": "plume", "allowed_main_stats": ["atk_flat"], "min_useful_substats": 2, "rationale_ru": "Основная характеристика пера фиксирована правилами игры."},
                    {"slot": "sands", "allowed_main_stats": ["atk_pct"], "min_useful_substats": 2, "rationale_ru": "Атака выбрана для первого проверяемого варианта этой сборки."},
                    {"slot": "goblet", "allowed_main_stats": ["pyro_dmg"], "min_useful_substats": 2, "rationale_ru": "Пиро-урон соответствует элементу и роли целевого персонажа."},
                    {"slot": "circlet", "allowed_main_stats": ["crit_rate"], "min_useful_substats": 2, "rationale_ru": "Шанс крита выбран из разрешённого профиля целевого персонажа."},
                ],
                "substat_priority_order": ["crit_rate", "crit_dmg", "atk_pct", "energy_recharge"],
                "slot_priority_order": ["circlet", "goblet", "sands", "plume", "flower"],
                "farming_plan_ru": "Сначала получить допустимую корону, затем проверять кубок и часы.",
                "alternative_upgrade_ru": "После проверки ротации сравнить артефакты с прокачкой талантов.",
                "preference_handling_ru": "Комментарий пользователя применён к первой рабочей сборке.",
                "assumptions_ru": ["Порог восстановления энергии пока не рассчитан."],
                "confidence": "medium",
            }, ensure_ascii=False),
            input_tokens=600,
            output_tokens=220,
            response_id="resp_web_artifact",
            web_search_used=True,
        )


class _RotationProvider:
    backend = LLMBackend.OPENAI_LUNA
    model = "web-rotation-test"

    def complete(self, request):
        return LLMCompletion(
            text=json.dumps({
                "domain_team": ["Mavuika", "Citlali", "Xilonen", "Bennett"],
                "opening_ru": "Сначала подготовить защиту и усиления перед окном Мавуики.",
                "steps": [
                    {"character_key": "Citlali", "action": "skill", "repetitions": 1, "purpose_ru": "Подготовить защиту перед главным окном команды."},
                    {"character_key": "Xilonen", "action": "skill", "repetitions": 1, "purpose_ru": "Активировать поддержку перед главным источником урона."},
                    {"character_key": "Bennett", "action": "burst", "repetitions": 1, "purpose_ru": "Открыть командное окно усиления и лечения."},
                    {"character_key": "Mavuika", "action": "skill", "repetitions": 1, "purpose_ru": "Подготовить состояние основного источника урона."},
                    {"character_key": "Mavuika", "action": "burst", "repetitions": 1, "purpose_ru": "Использовать главное окно урона после поддержки."},
                ],
                "burst_fallbacks": [
                    {"at_step": 3, "response": "use_skill_then_retry", "rationale_ru": "Навык даёт безопасный путь к повторной проверке ульты."},
                    {"at_step": 5, "response": "restart_rotation", "rationale_ru": "Без ульты нужно вернуться к подготовке команды."},
                ],
                "repeat_from_step": 1,
                "stop_conditions_ru": ["Остановиться, если действие не подтверждено наблюдением."],
                "preference_handling_ru": "Комментарий пользователя применён к безопасной ротации.",
                "assumptions_ru": ["Точные тайминги и энергия пока не рассчитаны."],
                "rationale_ru": "Команда готовит защиту и усиления до основного окна Мавуики.",
                "confidence": "medium",
            }, ensure_ascii=False),
            input_tokens=500,
            output_tokens=210,
            response_id="resp_web_rotation",
            web_search_used=True,
        )


def valid_good() -> dict[str, object]:
    slots = [
        ("flower", "hp"),
        ("plume", "atk"),
        ("sands", "atk_"),
        ("goblet", "pyro_dmg_"),
        ("circlet", "critRate_"),
    ]
    return {
        "format": "GOOD",
        "version": 1,
        "source": "API test",
        "artifacts": [
            {
                "setKey": "ObsidianCodex",
                "slotKey": slot,
                "level": 0,
                "rarity": 5,
                "mainStatKey": main,
                "substats": [
                    {"key": "critDMG_", "value": 7.8},
                    {
                        "key": "atk_" if main != "atk_" else "critRate_",
                        "value": 5.8,
                    },
                ],
            }
            for slot, main in slots
        ],
    }


@unittest.skipUnless(APP_TEST_DEPS_AVAILABLE, "install the app and test extras")
class WebAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.extractor = _VideoExtractor(valid_good())
        self.video_imports = VideoImportService(
            Path(self.directory.name) / "data",
            extractor_factory=lambda: self.extractor,
        )
        strategy_database = Path(self.directory.name) / "data" / "grindless.sqlite3"
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=create_app(
                    Path(self.directory.name) / "missing",
                    Path(self.directory.name) / "data",
                    video_import_service=self.video_imports,
                    enka_client=EnkaClient(lambda uid: {
                        "ttl": 0,
                        "avatarInfoList": [
                            {"avatarId": 10000106, "talentIdList": [1, 2], "equipList": []},
                            {"avatarId": 10000107, "equipList": []},
                            {"avatarId": 10000103, "equipList": []},
                            {"avatarId": 10000032, "equipList": []},
                        ],
                    }),
                    strategy_planner_factory=lambda backend: TeamStrategist(
                        AuditedLLM(
                            _StrategyProvider(),
                            SQLiteQuotaStore(strategy_database),
                        )
                    ),
                    artifact_planner_factory=lambda backend: ArtifactGoalPlanner(
                        AuditedLLM(
                            _ArtifactProvider(),
                            SQLiteQuotaStore(strategy_database),
                        )
                    ),
                    rotation_planner_factory=lambda backend: RotationPlanner(
                        AuditedLLM(
                            _RotationProvider(),
                            SQLiteQuotaStore(strategy_database),
                        )
                    ),
                )
            ),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.directory.cleanup()

    async def test_health_and_audit_contract(self) -> None:
        health = await self.client.get("/api/v1/health")
        analysis = await self.client.post(
            "/api/v1/audits/mavuika?policy=economy&top=5",
            json=valid_good(),
        )

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(health.json()["version"], "0.35.0")
        self.assertEqual(len(health.json()["llm_backends"]), 5)
        self.assertEqual(analysis.status_code, 200)
        body = analysis.json()
        self.assertEqual(body["inventory"]["artifacts"], 5)
        self.assertEqual(len(body["audit"]["selected_artifact_ids"]), 5)

    async def test_universal_onboarding_collects_enka_then_audits_target(self) -> None:
        catalog = await self.client.get("/api/v1/characters")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(len(catalog.json()["targets"]), 60)
        self.assertEqual(catalog.json()["roster_count"], 116)
        self.assertEqual(catalog.json()["roster_provenance"]["game_version"], "7.0")
        self.assertEqual(catalog.json()["target_profile_provenance"]["game_version"], "7.0")
        intent = {
            "target_key": "Mavuika",
            "target_team_mode": "manual",
            "target_team": ["Mavuika", "Citlali", "Xilonen", "Bennett"],
            "domain_team_mode": "same",
            "domain_team": [],
            "candidate_pool": [],
        }
        snapshot = await self.client.post(
            "/api/v1/profiles/enka/snapshots",
            headers={"X-GrindLess-Local": "1"},
            json={"uid": "700123456", "consent": True, "team_intent": intent},
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertTrue(snapshot.json()["complete"])
        analysis = await self.client.post(
            "/api/v1/characters/Mavuika/audit?policy=economy&top=5",
            json={
                "inventory": valid_good(),
                "team_intent": intent,
                "enka_collection_id": snapshot.json()["collection_id"],
            },
        )
        self.assertEqual(analysis.status_code, 200)
        self.assertEqual(analysis.json()["profile"]["constellation"], 2)
        self.assertEqual(analysis.json()["team_plan"]["target_objective"], "max_dps")

        strategy = await self.client.post(
            "/api/v1/team-strategies",
            json={
                "team_intent": intent,
                "enka_collection_id": snapshot.json()["collection_id"],
                "llm_backend": "openai_luna",
                "preferences": "Стабильность важнее рекорда.",
            },
        )
        self.assertEqual(strategy.status_code, 200)
        self.assertEqual(strategy.json()["decision_owner"], "llm_plus_team_evaluator")
        self.assertEqual(strategy.json()["execution_status"], "shadow_only")
        self.assertEqual(strategy.json()["llm_audit"]["successful_calls"], 1)
        self.assertEqual(strategy.json()["evaluation"]["evaluator"], "deterministic_rubric_v1")

    async def test_enka_first_onboarding_discovers_then_finalizes_selected_team(self) -> None:
        discovered = await self.client.post(
            "/api/v1/profiles/enka/snapshots",
            headers={"X-GrindLess-Local": "1"},
            json={
                "uid": "700123456",
                "consent": True,
                "mode": "discovery",
                "team_intent": None,
            },
        )

        self.assertEqual(discovered.status_code, 200)
        collection = discovered.json()
        self.assertEqual(collection["mode"], "discovery")
        self.assertFalse(collection["complete"])
        self.assertFalse(collection["finalized"])
        self.assertEqual(len(collection["observed_keys"]), 4)

        intent = {
            "target_key": "Mavuika",
            "target_objective": "max_dps",
            "target_team_mode": "auto",
            "target_team": [],
            "domain_team_mode": "same",
            "domain_objective": "stable_rotation",
            "domain_team": [],
            "candidate_pool": ["Citlali", "Xilonen", "Bennett"],
        }
        finalized = await self.client.post(
            f"/api/v1/profiles/enka/collections/{collection['collection_id']}/finalize",
            headers={"X-GrindLess-Local": "1"},
            json={"team_intent": intent},
        )

        self.assertEqual(finalized.status_code, 200)
        self.assertTrue(finalized.json()["complete"])
        self.assertTrue(finalized.json()["finalized"])

    async def test_game_adapter_status_fails_loudly_off_linux(self) -> None:
        response = await self.client.get("/api/v1/game-adapter/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(
            body["status"],
            {"unsupported", "setup_required", "game_not_running", "needs_attention", "ready"},
        )
        self.assertIn("checks", body)

    async def test_artifact_goal_is_validated_and_used_by_simulation(self) -> None:
        intent = {
            "target_key": "Mavuika",
            "target_team_mode": "manual",
            "target_team": ["Mavuika", "Citlali", "Xilonen", "Bennett"],
            "domain_team_mode": "same",
            "domain_team": [],
            "candidate_pool": [],
        }
        snapshot = await self.client.post(
            "/api/v1/profiles/enka/snapshots",
            headers={"X-GrindLess-Local": "1"},
            json={"uid": "700123456", "consent": True, "team_intent": intent},
        )
        inventory = valid_good()
        inventory["artifacts"].append({
            "setKey": "ObsidianCodex",
            "slotKey": "circlet",
            "level": 0,
            "rarity": 5,
            "mainStatKey": "atk_",
            "substats": [
                {"key": "critDMG_", "value": 7.8},
                {"key": "enerRech_", "value": 5.8},
            ],
        })

        planned = await self.client.post(
            "/api/v1/artifact-goal-strategies",
            json={
                "inventory": inventory,
                "team_intent": intent,
                "enka_collection_id": snapshot.json()["collection_id"],
                "llm_backend": "openai_luna",
                "policy": "economy",
                "preferences": "Нужна первая рабочая сборка.",
            },
        )

        self.assertEqual(planned.status_code, 200)
        plan = planned.json()
        self.assertEqual(plan["decision_owner"], "llm")
        self.assertEqual(
            plan["resolved_goal"]["constraints"]["set_requirements"],
            [{"set_name": "ObsidianCodex", "pieces": 4}],
        )
        self.assertEqual(
            plan["inventory_audit"]["candidates"]["circlet"][0]["main_stat"],
            "crit_rate",
        )
        self.assertEqual(plan["llm_audit"]["calls"][0]["purpose"], "artifact_goal_strategy")

        rotation_response = await self.client.post(
            "/api/v1/rotation-strategies",
            json={
                "team_intent": intent,
                "enka_collection_id": snapshot.json()["collection_id"],
                "llm_backend": "openai_luna",
                "artifact_goal": plan["resolved_goal"],
                "preferences": "Стабильная ротация без рискованных продолжений.",
            },
        )
        self.assertEqual(rotation_response.status_code, 200)
        rotation = rotation_response.json()
        self.assertEqual(rotation["validation"]["timing_status"], "web_researched")
        self.assertEqual(rotation["validated_rotation"]["input_authority"], "none")

        simulation = await self.client.post(
            "/api/v1/characters/Mavuika/simulation",
            json={
                "inventory": inventory,
                "policy": "economy",
                "target_slots": ["circlet"],
                "resin_budget": 20,
                "seed": 7,
                "llm_backend": "offline",
                "team_intent": intent,
                "enka_collection_id": snapshot.json()["collection_id"],
                "artifact_goal": plan["resolved_goal"],
                "rotation_plan": rotation["validated_rotation"],
            },
        )
        self.assertEqual(simulation.status_code, 200)
        self.assertEqual(simulation.json()["artifact_goal_source"], "llm")
        self.assertEqual(simulation.json()["rotation_plan_source"], "llm")
        self.assertEqual(simulation.json()["rotation_execution_status"], "not_executed")
        self.assertEqual(simulation.json()["baseline_artifact_ids"]["circlet"], plan["inventory_audit"]["selected_artifact_ids"]["circlet"])

    async def test_empty_inventory_returns_structured_422(self) -> None:
        payload = valid_good()
        payload["artifacts"] = []

        response = await self.client.post("/api/v1/audits/mavuika", json=payload)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "invalid_good")

    async def test_non_loopback_host_is_rejected(self) -> None:
        response = await self.client.get(
            "/api/v1/health",
            headers={"host": "attacker.example"},
        )

        self.assertEqual(response.status_code, 400)

    async def test_video_import_requires_local_header(self) -> None:
        response = await self.client.post(
            "/api/v1/video-imports",
            files={"video": ("inventory.mp4", b"video", "video/mp4")},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "local_header_required")

    async def test_video_import_returns_validated_good_and_removes_video(self) -> None:
        response = await self.client.post(
            "/api/v1/video-imports",
            headers={"X-GrindLess-Local": "1"},
            files={"video": ("inventory.mp4", b"video", "video/mp4")},
        )

        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job_id"]
        status: dict[str, object] = {}
        for _ in range(100):
            polled = await self.client.get(f"/api/v1/video-imports/{job_id}")
            status = polled.json()
            if status["status"] in {"succeeded", "failed"}:
                break
            await sleep(0.01)
        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["good"]["format"], "GOOD")
        self.assertIsNotNone(self.extractor.seen_path)
        self.assertFalse(self.extractor.seen_path.exists())

    async def test_simulation_contract_exposes_run_trace(self) -> None:
        response = await self.client.post(
            "/api/v1/simulations/mavuika",
            json={
                "inventory": valid_good(),
                "policy": "economy",
                "target_slots": ["sands"],
                "resin_budget": 60,
                "seed": 7,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["target_slots"], ["sands"])
        self.assertLessEqual(body["result"]["runs"], 3)
        self.assertEqual(len(body["runs"]), body["result"]["runs"])
        self.assertIn(
            body["result"]["reason"],
            {
                "all_slot_goals_met",
                "resin_exhausted",
            },
        )
        self.assertEqual(body["narration"]["status"], "offline")
        self.assertFalse(body["narration"]["external_data_sent"])
        self.assertTrue(body["session_id"])

        history = await self.client.get("/api/v1/sessions")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["sessions"]), 1)
        stored = await self.client.get(f"/api/v1/sessions/{body['session_id']}")
        self.assertEqual(stored.status_code, 200)
        self.assertEqual(stored.json()["payload"]["quota"]["used_today"], 0)

    async def test_simulation_accepts_inventory_without_target_set(self) -> None:
        inventory = valid_good()
        for artifact in inventory["artifacts"]:
            artifact["setKey"] = "GladiatorsFinale"

        response = await self.client.post(
            "/api/v1/simulations/mavuika",
            json={
                "inventory": inventory,
                "policy": "spend_all",
                "target_slots": ["flower", "plume", "sands", "goblet", "circlet"],
                "resin_budget": 20,
                "seed": 9,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result"]["runs"], 1)
        self.assertEqual(len(body["baseline_artifact_ids"]), 5)
        self.assertTrue(
            all(
                "valid baseline" in item["reason"] or not item["accepted"]
                for item in body["result"]["slot_progress"]
            )
        )

    async def test_unconfigured_luna_is_rejected_before_simulation(self) -> None:
        response = await self.client.post(
            "/api/v1/simulations/mavuika",
            json={
                "inventory": valid_good(),
                "policy": "economy",
                "target_slots": ["sands"],
                "resin_budget": 60,
                "seed": 7,
                "llm_backend": "openai_luna",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "llm_not_configured")

    async def test_simulation_rejects_fractional_reward_budget(self) -> None:
        response = await self.client.post(
            "/api/v1/simulations/mavuika",
            json={
                "inventory": valid_good(),
                "policy": "economy",
                "target_slots": ["sands"],
                "resin_budget": 55,
                "seed": 7,
            },
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
