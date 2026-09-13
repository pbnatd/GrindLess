from __future__ import annotations

import json

from .llm import AuditedLLM, LLMRequest, NarrationReport


class StructuredOutputError(RuntimeError):
    """A provider response could not become one validated JSON document."""

    def __init__(self, message: str, audit: NarrationReport) -> None:
        super().__init__(message)
        self.audit = audit


def complete_json_with_truncation_retry(
    llm: AuditedLLM,
    request: LLMRequest,
    *,
    recovery_input: str,
    recovery_tokens: int,
    recovery_purpose: str,
    recovery_schema_name: str,
    operation_label: str,
) -> object:
    """Return parsed JSON, retrying once only for a detectably cut-off response."""

    try:
        raw = llm.complete(request)
    except Exception as exc:
        raise StructuredOutputError(
            f"Не удалось подготовить раздел «{operation_label}»: {exc}",
            llm.report(),
        ) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        llm.invalidate_last_output(f"invalid JSON: {exc}")
        if not _looks_truncated(exc):
            raise StructuredOutputError(
                f"Не удалось обработать полученный ответ: {exc}", llm.report()
            ) from exc

    recovery = LLMRequest(
        purpose=recovery_purpose,
        input_text=recovery_input,
        max_output_tokens=recovery_tokens,
        response_schema=request.response_schema,
        response_schema_name=recovery_schema_name,
        reasoning_effort=request.reasoning_effort,
        web_search=request.web_search,
    )
    try:
        recovered = llm.complete(recovery)
        return json.loads(recovered)
    except Exception as exc:
        if isinstance(exc, json.JSONDecodeError):
            llm.invalidate_last_output(f"invalid recovery JSON: {exc}")
        raise StructuredOutputError(
            f"Не удалось обработать ответ после повторной попытки: {exc}",
            llm.report(),
        ) from exc


def _looks_truncated(error: json.JSONDecodeError) -> bool:
    if "Unterminated string" in error.msg:
        return True
    return error.pos >= max(0, len(error.doc) - 4)
