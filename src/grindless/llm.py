from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .models import SlotProgress
from .narrator import TemplateNarrator


class LLMBackend(StrEnum):
    OFFLINE = "offline"
    OPENAI_LUNA = "openai_luna"
    OPENAI_TERRA = "openai_terra"
    OPENAI_SOL = "openai_sol"
    LOCAL_QWEN = "local_qwen"


class ReasoningEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


OPENAI_BACKENDS = {
    LLMBackend.OPENAI_LUNA,
    LLMBackend.OPENAI_TERRA,
    LLMBackend.OPENAI_SOL,
}

OPENAI_MODEL_BY_BACKEND = {
    LLMBackend.OPENAI_LUNA: "gpt-5.6-luna",
    LLMBackend.OPENAI_TERRA: "gpt-5.6-terra",
    LLMBackend.OPENAI_SOL: "gpt-5.6-sol",
}


class LLMConfigurationError(RuntimeError):
    pass


class QuotaExceededError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMRequest:
    purpose: str
    input_text: str
    max_output_tokens: int = 600
    response_schema: dict[str, object] | None = None
    response_schema_name: str = "grindless_response"
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    web_search: bool = False


class WebSource(BaseModel):
    url: str
    title: str | None = None


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    response_id: str | None = None
    web_search_used: bool = False
    web_sources: tuple[WebSource, ...] = ()


class LLMProvider(Protocol):
    backend: LLMBackend
    model: str

    def complete(self, request: LLMRequest) -> LLMCompletion: ...


class QuotaSnapshot(BaseModel):
    daily_limit: int
    monthly_limit: int
    used_today: int
    used_this_month: int
    attempts_today: int
    input_tokens_this_month: int
    output_tokens_this_month: int
    resets_at_utc: str


class LLMCallAudit(BaseModel):
    purpose: str
    backend: LLMBackend
    model: str
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    status: str
    provider_called: bool
    transmitted_text: str
    output_text: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    response_id: str | None = None
    estimated_cost_usd: float | None = None
    web_search_used: bool = False
    web_sources: list[WebSource] = Field(default_factory=list)
    error: str | None = None


class NarrationReport(BaseModel):
    backend: LLMBackend
    model: str | None
    status: str
    external_data_sent: bool
    successful_calls: int
    failed_calls: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    pricing_note: str
    calls: list[LLMCallAudit] = Field(default_factory=list)


class BackendStatus(BaseModel):
    backend: LLMBackend
    label: str
    configured: bool
    model: str | None = None
    reason: str | None = None


class OpenAIResponsesProvider:
    """One Responses API implementation for OpenAI and local-compatible servers."""

    def __init__(
        self,
        *,
        backend: LLMBackend,
        model: str,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise LLMConfigurationError(
                    "LLM support is optional; install with: pip install -e '.[api]'"
                ) from exc
            kwargs: dict[str, Any] = {}
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["base_url"] = base_url
            client = OpenAI(**kwargs)
        self.backend = backend
        self.model = model
        self.client = client

    def complete(self, request: LLMRequest) -> LLMCompletion:
        request_arguments: dict[str, object] = {
            "model": self.model,
            "input": request.input_text,
            "max_output_tokens": request.max_output_tokens,
        }
        if self.backend in OPENAI_BACKENDS:
            request_arguments["reasoning"] = {"effort": request.reasoning_effort.value}
            if request.web_search:
                request_arguments["tools"] = [{"type": "web_search"}]
                request_arguments["tool_choice"] = "required"
                request_arguments["include"] = ["web_search_call.action.sources"]
        elif request.web_search:
            raise LLMConfigurationError(
                "live web research is available only for the OpenAI model options"
            )
        if (
            request.response_schema is not None
            and self.backend in OPENAI_BACKENDS
        ):
            request_arguments["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.response_schema_name,
                    "schema": request.response_schema,
                    "strict": False,
                }
            }
        response = self.client.responses.create(
            **request_arguments,
        )
        output_text = str(getattr(response, "output_text", "")).strip()
        if not output_text:
            raise RuntimeError("LLM provider returned no text")
        usage = getattr(response, "usage", None)
        web_search_used, web_sources = _extract_web_research(response)
        return LLMCompletion(
            text=output_text,
            input_tokens=int(_usage_value(usage, "input_tokens")),
            output_tokens=int(_usage_value(usage, "output_tokens")),
            cached_input_tokens=int(_cached_input_tokens(usage)),
            response_id=(str(response.id) if getattr(response, "id", None) else None),
            web_search_used=web_search_used,
            web_sources=tuple(web_sources),
        )


class SQLiteQuotaStore:
    """Atomic one-user quota ledger; replaceable by a server-side store later."""

    def __init__(
        self,
        database_path: Path,
        *,
        daily_limit: int = 40,
        monthly_limit: int = 400,
    ) -> None:
        self.database_path = database_path
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self._initialize()

    def reserve(self, provider: LLMProvider, request: LLMRequest) -> str:
        now = datetime.now(UTC)
        reservation_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            stale_before = (now - timedelta(minutes=10)).isoformat()
            connection.execute(
                """
                UPDATE llm_calls
                SET status='failed', error='stale reservation recovered'
                WHERE status='reserved' AND created_at < ?
                """,
                (stale_before,),
            )
            used_today = self._count_active(
                connection, "day_key", now.date().isoformat()
            )
            used_month = self._count_active(
                connection, "month_key", now.strftime("%Y-%m")
            )
            if used_today >= self.daily_limit:
                raise QuotaExceededError("daily LLM call limit is exhausted")
            if used_month >= self.monthly_limit:
                raise QuotaExceededError("monthly LLM call limit is exhausted")
            connection.execute(
                """
                INSERT INTO llm_calls (
                    id, created_at, day_key, month_key, backend, model, purpose,
                    status, input_chars, max_output_tokens
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)
                """,
                (
                    reservation_id,
                    now.isoformat(),
                    now.date().isoformat(),
                    now.strftime("%Y-%m"),
                    provider.backend.value,
                    provider.model,
                    request.purpose,
                    len(request.input_text),
                    request.max_output_tokens,
                ),
            )
        return reservation_id

    def commit(self, reservation_id: str, completion: LLMCompletion) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE llm_calls
                SET status='succeeded', input_tokens=?, output_tokens=?, response_id=?
                WHERE id=? AND status='reserved'
                """,
                (
                    completion.input_tokens,
                    completion.output_tokens,
                    completion.response_id,
                    reservation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("unknown or completed LLM quota reservation")

    def fail(self, reservation_id: str, error: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE llm_calls SET status='failed', error=? WHERE id=? AND status='reserved'",
                (error[:1000], reservation_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("unknown or completed LLM quota reservation")

    def snapshot(self) -> QuotaSnapshot:
        now = datetime.now(UTC)
        day_key = now.date().isoformat()
        month_key = now.strftime("%Y-%m")
        with self._connect() as connection:
            used_today = self._count_succeeded(connection, "day_key", day_key)
            used_month = self._count_succeeded(connection, "month_key", month_key)
            attempts_today = int(
                connection.execute(
                    "SELECT COUNT(*) FROM llm_calls WHERE day_key=?", (day_key,)
                ).fetchone()[0]
            )
            tokens = connection.execute(
                """
                SELECT COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
                FROM llm_calls WHERE month_key=? AND status='succeeded'
                """,
                (month_key,),
            ).fetchone()
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
        else:
            next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
        return QuotaSnapshot(
            daily_limit=self.daily_limit,
            monthly_limit=self.monthly_limit,
            used_today=used_today,
            used_this_month=used_month,
            attempts_today=attempts_today,
            input_tokens_this_month=int(tokens[0]),
            output_tokens_this_month=int(tokens[1]),
            resets_at_utc=next_month.isoformat(),
        )

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    day_key TEXT NOT NULL,
                    month_key TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    model TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_chars INTEGER NOT NULL,
                    max_output_tokens INTEGER NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    response_id TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_calls_day ON llm_calls(day_key, status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_calls_month ON llm_calls(month_key, status)"
            )
        try:
            self.database_path.chmod(0o600)
        except OSError:
            pass

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _count_active(connection: sqlite3.Connection, column: str, key: str) -> int:
        if column not in {"day_key", "month_key"}:
            raise ValueError("unsupported quota period")
        return int(
            connection.execute(
                f"SELECT COUNT(*) FROM llm_calls WHERE {column}=? AND status IN ('reserved','succeeded')",
                (key,),
            ).fetchone()[0]
        )

    @staticmethod
    def _count_succeeded(connection: sqlite3.Connection, column: str, key: str) -> int:
        if column not in {"day_key", "month_key"}:
            raise ValueError("unsupported quota period")
        return int(
            connection.execute(
                f"SELECT COUNT(*) FROM llm_calls WHERE {column}=? AND status='succeeded'",
                (key,),
            ).fetchone()[0]
        )


class AuditedLLM:
    """Quota-controlled provider whose every call is reconstructable from evidence."""

    def __init__(
        self,
        provider: LLMProvider,
        quota: SQLiteQuotaStore,
        *,
        input_usd_per_million: float | None = None,
        cached_input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
        pricing_note: str = "not_calculated_prices_not_configured",
    ) -> None:
        if (input_usd_per_million is None) != (output_usd_per_million is None):
            raise LLMConfigurationError(
                "both input and output token prices must be configured together"
            )
        if input_usd_per_million is not None and (
            input_usd_per_million < 0
            or output_usd_per_million is None
            or output_usd_per_million < 0
            or (
                cached_input_usd_per_million is not None
                and cached_input_usd_per_million < 0
            )
        ):
            raise LLMConfigurationError("token prices cannot be negative")
        self.provider = provider
        self.quota = quota
        self.input_usd_per_million = input_usd_per_million
        self.cached_input_usd_per_million = (
            cached_input_usd_per_million
            if cached_input_usd_per_million is not None
            else input_usd_per_million
        )
        self.output_usd_per_million = output_usd_per_million
        self.pricing_note = pricing_note
        self.calls: list[LLMCallAudit] = []

    def complete(self, request: LLMRequest) -> str:
        reservation_id: str | None = None
        try:
            reservation_id = self.quota.reserve(self.provider, request)
        except Exception as exc:
            self.calls.append(
                LLMCallAudit(
                    purpose=request.purpose,
                    backend=self.provider.backend,
                    model=self.provider.model,
                    reasoning_effort=request.reasoning_effort,
                    status="failed",
                    provider_called=False,
                    transmitted_text=request.input_text,
                    error=str(exc),
                )
            )
            raise

        try:
            completion = self.provider.complete(request)
            self.quota.commit(reservation_id, completion)
        except Exception as exc:
            try:
                self.quota.fail(reservation_id, str(exc))
            except Exception:  # noqa: BLE001, S110 - preserve the provider failure
                pass
            self.calls.append(
                LLMCallAudit(
                    purpose=request.purpose,
                    backend=self.provider.backend,
                    model=self.provider.model,
                    reasoning_effort=request.reasoning_effort,
                    status="failed",
                    provider_called=True,
                    transmitted_text=request.input_text,
                    error=str(exc),
                )
            )
            raise

        self.calls.append(
            LLMCallAudit(
                purpose=request.purpose,
                backend=self.provider.backend,
                model=self.provider.model,
                reasoning_effort=request.reasoning_effort,
                status="succeeded",
                provider_called=True,
                transmitted_text=request.input_text,
                output_text=completion.text,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                cached_input_tokens=completion.cached_input_tokens,
                response_id=completion.response_id,
                estimated_cost_usd=self._estimated_cost(completion),
                web_search_used=completion.web_search_used,
                web_sources=list(completion.web_sources),
            )
        )
        return completion.text

    def report(self) -> NarrationReport:
        failed = sum(item.status != "succeeded" for item in self.calls)
        input_tokens = sum(item.input_tokens for item in self.calls)
        output_tokens = sum(item.output_tokens for item in self.calls)
        costs = [
            item.estimated_cost_usd
            for item in self.calls
            if item.estimated_cost_usd is not None
        ]
        return NarrationReport(
            backend=self.provider.backend,
            model=self.provider.model,
            status="degraded" if failed else "succeeded",
            external_data_sent=any(item.provider_called for item in self.calls),
            successful_calls=len(self.calls) - failed,
            failed_calls=failed,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost_usd=(sum(costs) if len(costs) == len(self.calls) else None),
            pricing_note=(
                self.pricing_note
                if self.input_usd_per_million is not None
                else "not_calculated_prices_not_configured"
            ),
            calls=self.calls,
        )

    def invalidate_last_output(self, error: str) -> None:
        """Record a provider response that was billable but unusable by the agent."""
        if not self.calls or self.calls[-1].status != "succeeded":
            raise RuntimeError("no successful LLM output is available to invalidate")
        self.calls[-1].status = "invalid_output"
        self.calls[-1].error = error[:1_000]

    def _estimated_cost(self, completion: LLMCompletion) -> float | None:
        if self.input_usd_per_million is None or self.output_usd_per_million is None:
            return None
        uncached_input = max(0, completion.input_tokens - completion.cached_input_tokens)
        cached_rate = (
            self.cached_input_usd_per_million
            if self.cached_input_usd_per_million is not None
            else self.input_usd_per_million
        )
        return round(
            (
                uncached_input * self.input_usd_per_million
                + completion.cached_input_tokens * cached_rate
                + completion.output_tokens * self.output_usd_per_million
            )
            / 1_000_000,
            8,
        )


class AuditedNarrator(AuditedLLM):
    """Compatibility narrator that degrades to a local explanation template."""

    def __init__(
        self,
        provider: LLMProvider,
        quota: SQLiteQuotaStore,
        *,
        input_usd_per_million: float | None = None,
        cached_input_usd_per_million: float | None = None,
        output_usd_per_million: float | None = None,
        pricing_note: str = "not_calculated_prices_not_configured",
    ) -> None:
        super().__init__(
            provider,
            quota,
            input_usd_per_million=input_usd_per_million,
            cached_input_usd_per_million=cached_input_usd_per_million,
            output_usd_per_million=output_usd_per_million,
            pricing_note=pricing_note,
        )
        self.fallback = TemplateNarrator()

    def checkpoint(self, run_number: int, progress: list[SlotProgress]) -> str:
        evidence = [item.model_dump(mode="json") for item in progress]
        prompt = (
            "Кратко объясни контрольное решение GrindLess на русском. "
            "Не пересчитывай метрики и не прогнозируй результат улучшения предметов. "
            f"Прогон: {run_number}. Данные сессии: "
            f"{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}"
        )
        return self._complete(
            LLMRequest(purpose=f"checkpoint_{run_number}", input_text=prompt),
            self.fallback.checkpoint(run_number, progress),
        )

    def final(self, result_summary: dict[str, object]) -> str:
        prompt = (
            "Кратко объясни финальное решение GrindLess на русском, строго по "
            "структурированному результату: "
            f"{json.dumps(result_summary, ensure_ascii=False, sort_keys=True)}"
        )
        return self._complete(
            LLMRequest(purpose="final_explanation", input_text=prompt),
            self.fallback.final(result_summary),
        )

    def _complete(self, request: LLMRequest, fallback: str) -> str:
        try:
            return self.complete(request)
        except Exception:  # noqa: BLE001 - narration degrades, strategy fails loud
            return fallback


class LLMRuntime:
    def __init__(self, data_directory: Path | None = None) -> None:
        directory = data_directory or Path(
            os.environ.get("GRINDLESS_DATA_DIR", Path.home() / ".grindless")
        )
        self.quota = SQLiteQuotaStore(directory / "grindless.sqlite3")

    def statuses(self) -> list[BackendStatus]:
        qwen_model = os.environ.get("GRINDLESS_QWEN_MODEL", "Qwen/Qwen3-8B")
        openai_configured = bool(os.environ.get("OPENAI_API_KEY"))
        openai_reason = (
            None
            if openai_configured
            else "OPENAI_API_KEY is not configured for the local process."
        )
        return [
            BackendStatus(
                backend=LLMBackend.OFFLINE,
                label="Offline · deterministic",
                configured=True,
                reason="No model call; decisions and template explanations stay local.",
            ),
            BackendStatus(
                backend=LLMBackend.OPENAI_LUNA,
                label="Luna · быстро",
                configured=openai_configured,
                model=OPENAI_MODEL_BY_BACKEND[LLMBackend.OPENAI_LUNA],
                reason=openai_reason,
            ),
            BackendStatus(
                backend=LLMBackend.OPENAI_TERRA,
                label="Terra · баланс",
                configured=openai_configured,
                model=OPENAI_MODEL_BY_BACKEND[LLMBackend.OPENAI_TERRA],
                reason=openai_reason,
            ),
            BackendStatus(
                backend=LLMBackend.OPENAI_SOL,
                label="Sol · глубже",
                configured=openai_configured,
                model=OPENAI_MODEL_BY_BACKEND[LLMBackend.OPENAI_SOL],
                reason=openai_reason,
            ),
            BackendStatus(
                backend=LLMBackend.LOCAL_QWEN,
                label="Qwen · local server",
                configured=bool(os.environ.get("GRINDLESS_QWEN_BASE_URL")),
                model=qwen_model,
                reason=(
                    None
                    if os.environ.get("GRINDLESS_QWEN_BASE_URL")
                    else "GRINDLESS_QWEN_BASE_URL is not configured."
                ),
            ),
        ]

    def narrator(self, backend: LLMBackend) -> AuditedNarrator:
        provider, pricing = self._provider(backend)
        return AuditedNarrator(provider, self.quota, **pricing)

    def audited(self, backend: LLMBackend) -> AuditedLLM:
        provider, pricing = self._provider(backend)
        return AuditedLLM(provider, self.quota, **pricing)

    @staticmethod
    def _provider(
        backend: LLMBackend,
    ) -> tuple[LLMProvider, dict[str, float | str | None]]:
        if backend is LLMBackend.OFFLINE:
            raise LLMConfigurationError(
                "стратегический план требует Luna, Terra или Sol"
            )
        if backend in OPENAI_BACKENDS:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise LLMConfigurationError(
                    "OpenAI models are not configured: add an API key first"
                )
            provider = OpenAIResponsesProvider(
                backend=backend,
                model=OPENAI_MODEL_BY_BACKEND[backend],
                api_key=api_key,
            )
            return provider, _openai_pricing(provider.model)
        base_url = os.environ.get("GRINDLESS_QWEN_BASE_URL")
        if not base_url:
            raise LLMConfigurationError(
                "Local Qwen is not configured: set its server URL first"
            )
        provider = OpenAIResponsesProvider(
            backend=backend,
            model=os.environ.get("GRINDLESS_QWEN_MODEL", "Qwen/Qwen3-8B"),
            api_key=os.environ.get("GRINDLESS_QWEN_API_KEY", "local"),
            base_url=base_url,
        )
        return provider, {}


def offline_narration_report() -> NarrationReport:
    return NarrationReport(
        backend=LLMBackend.OFFLINE,
        model=None,
        status="offline",
        external_data_sent=False,
        successful_calls=0,
        failed_calls=0,
        pricing_note="not_applicable_offline",
    )


def _usage_value(usage: object, field: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        return int(usage.get(field, 0) or 0)
    return int(getattr(usage, field, 0) or 0)


def _cached_input_tokens(usage: object) -> int:
    if usage is None:
        return 0
    details = (
        usage.get("input_tokens_details")
        if isinstance(usage, dict)
        else getattr(usage, "input_tokens_details", None)
    )
    return _usage_value(details, "cached_tokens")


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _extract_web_research(response: object) -> tuple[bool, list[WebSource]]:
    """Extract provider-owned web evidence without trusting generated JSON fields."""

    output = _field(response, "output", [])
    if not isinstance(output, (list, tuple)):
        return False, []
    used = False
    sources: dict[str, WebSource] = {}
    for item in output:
        if _field(item, "type") == "web_search_call":
            used = True
            action = _field(item, "action", {})
            consulted = _field(action, "sources", [])
            if isinstance(consulted, (list, tuple)):
                for source in consulted:
                    url = _field(source, "url")
                    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                        continue
                    title = _field(source, "title")
                    sources[url] = WebSource(
                        url=url,
                        title=title if isinstance(title, str) and title.strip() else None,
                    )
        content = _field(item, "content", [])
        if not isinstance(content, (list, tuple)):
            continue
        for block in content:
            annotations = _field(block, "annotations", [])
            if not isinstance(annotations, (list, tuple)):
                continue
            for annotation in annotations:
                if _field(annotation, "type") != "url_citation":
                    continue
                citation = _field(annotation, "url_citation", annotation)
                url = _field(citation, "url")
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                title = _field(citation, "title")
                sources[url] = WebSource(
                    url=url,
                    title=title if isinstance(title, str) and title.strip() else None,
                )
    return used, list(sources.values())


def _openai_pricing(model: str) -> dict[str, float | str | None]:
    input_raw = os.environ.get("GRINDLESS_OPENAI_INPUT_USD_PER_MILLION")
    output_raw = os.environ.get("GRINDLESS_OPENAI_OUTPUT_USD_PER_MILLION")
    cached_raw = os.environ.get("GRINDLESS_OPENAI_CACHED_INPUT_USD_PER_MILLION")
    if input_raw is None and output_raw is None and cached_raw is None:
        if model == "gpt-5.6-luna":
            return {
                "input_usd_per_million": 0.20,
                "cached_input_usd_per_million": 0.02,
                "output_usd_per_million": 1.20,
                "pricing_note": "openai_public_pricing_2026-09-09",
            }
        return {
            "input_usd_per_million": None,
            "cached_input_usd_per_million": None,
            "output_usd_per_million": None,
            "pricing_note": "not_calculated_prices_not_configured",
        }
    if input_raw is None or output_raw is None:
        raise LLMConfigurationError(
            "configure both OpenAI input and output prices per million tokens"
        )
    try:
        return {
            "input_usd_per_million": float(input_raw),
            "cached_input_usd_per_million": (
                float(cached_raw) if cached_raw is not None else float(input_raw)
            ),
            "output_usd_per_million": float(output_raw),
            "pricing_note": "estimate_from_configured_per_million_prices",
        }
    except ValueError as exc:
        raise LLMConfigurationError("configured OpenAI token prices must be numbers") from exc
