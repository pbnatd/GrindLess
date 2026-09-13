from __future__ import annotations

import os
import webbrowser
from importlib.metadata import version as package_version
from pathlib import Path
from threading import Timer
from typing import Any, Callable

from .application import (
    CharacterFarmSimulationRequest,
    CharacterInventoryAnalysisRequest,
    MavuikaFarmSimulationRequest,
    analyze_character_inventory,
    analyze_mavuika_inventory,
    describe_character_preset,
    describe_mavuika_preset,
    simulate_character_farm,
    simulate_mavuika_farm,
)
from .artifact_strategy import (
    ArtifactGoalOutputError,
    ArtifactGoalPlanner,
    ArtifactGoalRequest,
)
from .character_catalog import (
    CHARACTERS,
    ROSTER_PROVENANCE,
    TARGET_CHARACTER_KEYS,
    TARGET_PROFILE_PROVENANCE,
    TeamIntent,
    build_team_plan,
)
from .enka import (
    EnkaClient,
    EnkaCollectionFinalizeRequest,
    EnkaCollectionRegistry,
    EnkaError,
    EnkaSnapshotRequest,
)
from .llm import (
    LLMBackend,
    LLMConfigurationError,
    LLMRuntime,
    offline_narration_report,
)
from .models import FarmPolicy
from .linux_game_adapter import probe_linux_game
from .platform_support import platform_support
from .rotation_strategy import (
    RotationOutputError,
    RotationPlanner,
    RotationStrategyRequest,
)
from .session_store import SQLiteSessionStore
from .strategy import StrategyOutputError, TeamStrategist, TeamStrategyRequest
from .video_import import VideoImportBusyError, VideoImportService

MAX_VIDEO_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
GRINDLESS_VERSION = package_version("grindless-agent")


def server_port_from_environment() -> int:
    raw = os.environ.get("GRINDLESS_PORT", "8765")
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError("GRINDLESS_PORT must be an integer") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("GRINDLESS_PORT must be between 1 and 65535")
    return port


def create_app(
    frontend_directory: Path | None = None,
    data_directory: Path | None = None,
    video_import_service: VideoImportService | None = None,
    enka_client: EnkaClient | None = None,
    strategy_planner_factory: Callable[[LLMBackend], TeamStrategist] | None = None,
    artifact_planner_factory: Callable[[LLMBackend], ArtifactGoalPlanner] | None = None,
    rotation_planner_factory: Callable[[LLMBackend], RotationPlanner] | None = None,
) -> Any:
    try:
        from fastapi import FastAPI, File, Header, HTTPException, Query
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import ValidationError
        from starlette.middleware.trustedhost import TrustedHostMiddleware
    except ImportError as exc:
        raise RuntimeError(
            "The local interface needs the optional app dependencies; "
            "install them with: pip install -e '.[app]'"
        ) from exc

    app = FastAPI(
        title="GrindLess local API",
        version=GRINDLESS_VERSION,
        description="Local UI boundary over the deterministic GrindLess core.",
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    llm_runtime = LLMRuntime(data_directory)
    session_store = SQLiteSessionStore(llm_runtime.quota.database_path)
    imports = video_import_service or VideoImportService(
        llm_runtime.quota.database_path.parent
    )
    enka = enka_client or EnkaClient()
    enka_collections = EnkaCollectionRegistry()

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "version": GRINDLESS_VERSION,
            "platform": platform_support().as_dict(),
            "llm_backends": [
                item.model_dump(mode="json") for item in llm_runtime.statuses()
            ],
        }

    @app.get("/api/v1/llm/status")
    def llm_status() -> dict[str, object]:
        return {
            "backends": [
                item.model_dump(mode="json") for item in llm_runtime.statuses()
            ],
            "quota": llm_runtime.quota.snapshot().model_dump(mode="json"),
            "quota_scope": "single_local_user",
        }

    @app.get("/api/v1/game-adapter/status")
    def game_adapter_status() -> dict[str, object]:
        return probe_linux_game().as_dict()

    @app.get("/api/v1/characters")
    def characters() -> dict[str, object]:
        return {
            "targets": [
                CHARACTERS[key].model_dump(mode="json")
                for key in TARGET_CHARACTER_KEYS
            ],
            "roster": [
                item.model_dump(mode="json")
                for item in sorted(CHARACTERS.values(), key=lambda value: value.name_ru)
            ],
            "roster_count": len(CHARACTERS),
            "roster_provenance": ROSTER_PROVENANCE,
            "target_profile_provenance": TARGET_PROFILE_PROVENANCE,
        }

    @app.post("/api/v1/team-plans")
    def team_plan(intent: TeamIntent) -> dict[str, object]:
        return build_team_plan(intent).model_dump(mode="json")

    @app.post("/api/v1/team-strategies")
    def team_strategy(request: TeamStrategyRequest) -> dict[str, object]:
        try:
            if request.llm_backend is LLMBackend.OFFLINE:
                raise LLMConfigurationError(
                    "стратегический план требует Luna, Terra или Sol"
                )
            profiles = enka_collections.profiles(request.enka_collection_id)
            planner = (
                strategy_planner_factory(request.llm_backend)
                if strategy_planner_factory is not None
                else TeamStrategist(llm_runtime.audited(request.llm_backend))
            )
            result = planner.plan(
                request.team_intent,
                profiles,
                request.preferences,
                request.reasoning_effort,
            )
            return result.model_dump(mode="json")
        except LLMConfigurationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "llm_not_configured", "message": str(exc)},
            ) from exc
        except StrategyOutputError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_strategy_output",
                    "message": str(exc),
                    "llm_audit": exc.audit.model_dump(mode="json"),
                },
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_strategy_input", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/artifact-goal-strategies")
    def artifact_goal_strategy(request: ArtifactGoalRequest) -> dict[str, object]:
        try:
            if request.llm_backend is LLMBackend.OFFLINE:
                raise LLMConfigurationError(
                    "artifact goal planning requires GPT Luna or local Qwen"
                )
            profiles = enka_collections.profiles(request.enka_collection_id)
            planner = (
                artifact_planner_factory(request.llm_backend)
                if artifact_planner_factory is not None
                else ArtifactGoalPlanner(llm_runtime.audited(request.llm_backend))
            )
            result = planner.plan(
                request.inventory,
                request.team_intent,
                profiles,
                policy=request.policy,
                preferences=request.preferences,
                reasoning_effort=request.reasoning_effort,
            )
            return result.model_dump(mode="json")
        except LLMConfigurationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "llm_not_configured", "message": str(exc)},
            ) from exc
        except ArtifactGoalOutputError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_artifact_goal_output",
                    "message": str(exc),
                    "llm_audit": exc.audit.model_dump(mode="json"),
                },
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_artifact_goal_input", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/rotation-strategies")
    def rotation_strategy(request: RotationStrategyRequest) -> dict[str, object]:
        try:
            if request.llm_backend is LLMBackend.OFFLINE:
                raise LLMConfigurationError(
                    "rotation planning requires GPT Luna or local Qwen"
                )
            profiles = enka_collections.profiles(request.enka_collection_id)
            planner = (
                rotation_planner_factory(request.llm_backend)
                if rotation_planner_factory is not None
                else RotationPlanner(llm_runtime.audited(request.llm_backend))
            )
            result = planner.plan(
                request.team_intent,
                profiles,
                artifact_goal=request.artifact_goal,
                preferences=request.preferences,
                reasoning_effort=request.reasoning_effort,
            )
            return result.model_dump(mode="json")
        except LLMConfigurationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "llm_not_configured", "message": str(exc)},
            ) from exc
        except RotationOutputError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_rotation_output",
                    "message": str(exc),
                    "llm_audit": exc.audit.model_dump(mode="json"),
                },
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_rotation_input", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/profiles/enka/snapshots")
    def enka_snapshot(
        request: EnkaSnapshotRequest,
        x_grindless_local: str = Header(default=""),
    ) -> dict[str, object]:
        if x_grindless_local != "1":
            raise HTTPException(
                status_code=403,
                detail={"code": "local_header_required", "message": "локальный заголовок отсутствует"},
            )
        try:
            showcase = enka.fetch_showcase(request.uid, consent=request.consent)
            return enka_collections.merge(
                request.uid,
                showcase,
                request.team_intent,
                request.collection_id,
                mode=request.mode,
            ).model_dump(mode="json")
        except (EnkaError, ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "enka_snapshot_failed", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/profiles/enka/collections/{collection_id}/finalize")
    def finalize_enka_collection(
        collection_id: str,
        request: EnkaCollectionFinalizeRequest,
        x_grindless_local: str = Header(default=""),
    ) -> dict[str, object]:
        if x_grindless_local != "1":
            raise HTTPException(
                status_code=403,
                detail={"code": "local_header_required", "message": "локальный заголовок отсутствует"},
            )
        try:
            return enka_collections.finalize(
                collection_id,
                request.team_intent,
            ).model_dump(mode="json")
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "enka_collection_finalize_failed", "message": str(exc)},
            ) from exc

    @app.get("/api/v1/characters/{character_key}/preset")
    def character_preset(
        character_key: str,
        policy: FarmPolicy = Query(default=FarmPolicy.ECONOMY),
    ) -> dict[str, object]:
        try:
            character, goals = describe_character_preset(character_key, policy)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"code": "unknown_target", "message": str(exc)}) from exc
        return {
            "character": character.model_dump(mode="json"),
            "policy": policy.value,
            "goals": [goal.model_dump(mode="json") for goal in goals],
        }

    @app.post("/api/v1/characters/{character_key}/audit")
    def audit_character(
        character_key: str,
        request: CharacterInventoryAnalysisRequest,
        policy: FarmPolicy = Query(default=FarmPolicy.ECONOMY),
        top: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, object]:
        try:
            if request.team_intent.target_key != character_key:
                raise ValueError("path character and selected target do not match")
            profile = enka_collections.target_profile(
                request.enka_collection_id,
                character_key,
            )
            if profile is None:
                raise ValueError("целевой персонаж не найден в собранных Enka-витринах")
            result = analyze_character_inventory(
                request.inventory,
                team_intent=request.team_intent,
                profile=profile,
                policy=policy,
                top_per_slot=top,
            )
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_character_audit", "message": str(exc)},
            ) from exc
        return result.model_dump(mode="json")

    @app.get("/api/v1/presets/mavuika")
    def mavuika_preset(
        policy: FarmPolicy = Query(default=FarmPolicy.ECONOMY),
    ) -> dict[str, object]:
        preset, goals = describe_mavuika_preset(policy)
        return {
            "preset": preset.model_dump(mode="json"),
            "policy": policy.value,
            "goals": [goal.model_dump(mode="json") for goal in goals],
        }

    @app.post("/api/v1/audits/mavuika")
    def audit_mavuika(
        payload: dict[str, Any],
        policy: FarmPolicy = Query(default=FarmPolicy.ECONOMY),
        top: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, object]:
        try:
            result = analyze_mavuika_inventory(
                payload,
                policy=policy,
                top_per_slot=top,
            )
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_good", "message": str(exc)},
            ) from exc
        return result.model_dump(mode="json")

    @app.post("/api/v1/video-imports", status_code=202)
    async def create_video_import(
        video: Any = File(...),
        x_grindless_local: str = Header(default=""),
    ) -> dict[str, object]:
        if x_grindless_local != "1":
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "local_header_required",
                    "message": "локальный заголовок отсутствует",
                },
            )
        try:
            job_id, target = imports.create_upload(video.filename or "")
        except VideoImportBusyError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "video_import_busy", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "unsupported_video", "message": str(exc)},
            ) from exc

        written = 0
        try:
            with target.open("xb") as output:
                while chunk := await video.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_VIDEO_UPLOAD_BYTES:
                        raise ValueError("видео превышает локальный лимит 2 ГиБ")
                    output.write(chunk)
            if written == 0:
                raise ValueError("выбран пустой видеофайл")
            imports.start(job_id)
        except Exception as exc:
            imports.discard(job_id)
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_video_upload", "message": str(exc)},
            ) from exc
        finally:
            await video.close()
        return {"job_id": job_id, "status": "queued"}

    @app.get("/api/v1/video-imports/{job_id}")
    def video_import(job_id: str) -> dict[str, object]:
        try:
            return imports.get(job_id).model_dump(mode="json")
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "video_import_not_found",
                    "message": "видеоскан не найден",
                },
            ) from exc

    @app.post("/api/v1/simulations/mavuika")
    def simulate_mavuika(
        request: MavuikaFarmSimulationRequest,
    ) -> dict[str, object]:
        try:
            if request.llm_backend is LLMBackend.OFFLINE:
                narrator = None
                narration = offline_narration_report()
            else:
                narrator = llm_runtime.narrator(request.llm_backend)
                narration = None
            result = simulate_mavuika_farm(request, narrator=narrator)
            if narrator is not None:
                narration = narrator.report()
            if narration is None:
                raise RuntimeError("narration report was not produced")
            payload = result.model_dump(mode="json")
            payload["narration"] = narration.model_dump(mode="json")
            payload["quota"] = llm_runtime.quota.snapshot().model_dump(mode="json")
            summary = session_store.save(payload)
            payload["session_id"] = summary.session_id
            return payload
        except LLMConfigurationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "llm_not_configured", "message": str(exc)},
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_simulation", "message": str(exc)},
            ) from exc

    @app.post("/api/v1/characters/{character_key}/simulation")
    def simulate_character(
        character_key: str,
        request: CharacterFarmSimulationRequest,
    ) -> dict[str, object]:
        try:
            if request.team_intent.target_key != character_key:
                raise ValueError("path character and selected target do not match")
            profile = enka_collections.target_profile(
                request.enka_collection_id,
                character_key,
            )
            if profile is None:
                raise ValueError("целевой персонаж не найден в собранных Enka-витринах")
            if request.llm_backend is LLMBackend.OFFLINE:
                narrator = None
                narration = offline_narration_report()
            else:
                narrator = llm_runtime.narrator(request.llm_backend)
                narration = None
            result = simulate_character_farm(request, profile=profile, narrator=narrator)
            if narrator is not None:
                narration = narrator.report()
            if narration is None:
                raise RuntimeError("narration report was not produced")
            payload = result.model_dump(mode="json")
            payload["narration"] = narration.model_dump(mode="json")
            payload["quota"] = llm_runtime.quota.snapshot().model_dump(mode="json")
            summary = session_store.save(payload)
            payload["session_id"] = summary.session_id
            return payload
        except LLMConfigurationError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "llm_not_configured", "message": str(exc)},
            ) from exc
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_simulation", "message": str(exc)},
            ) from exc

    @app.get("/api/v1/sessions")
    def sessions(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return {
            "sessions": [
                item.model_dump(mode="json") for item in session_store.list(limit)
            ]
        }

    @app.get("/api/v1/sessions/{session_id}")
    def session(session_id: str) -> dict[str, object]:
        try:
            stored = session_store.get(session_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "session_not_found", "message": str(exc)},
            ) from exc
        return stored.model_dump(mode="json")

    frontend = frontend_directory or (
        Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    if frontend.is_dir():
        assets = frontend / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend_route(path: str) -> Any:
            requested = (frontend / path).resolve()
            if (
                path
                and requested.is_relative_to(frontend.resolve())
                and requested.is_file()
            ):
                return FileResponse(requested)
            return FileResponse(frontend / "index.html")

    return app


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Install the local interface dependencies with: pip install -e '.[app]'"
        ) from exc

    port = server_port_from_environment()
    application_url = f"http://127.0.0.1:{port}"
    if os.environ.get("GRINDLESS_NO_BROWSER") != "1":
        Timer(1.0, lambda: webbrowser.open(application_url)).start()

    uvicorn.run(
        "grindless.web_app:create_app",
        factory=True,
        host="127.0.0.1",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
