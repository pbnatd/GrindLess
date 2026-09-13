from __future__ import annotations

import json
from typing import Any

from .llm import LLMBackend, LLMRequest, OpenAIResponsesProvider
from .models import SlotProgress


class OpenAINarrator:
    """Optional Responses API narrator for local, explicitly enabled test runs.

    Production multi-user use must route through the quota gateway described in
    the design doc; a shared API key must not be shipped in the desktop app.
    """

    def __init__(
        self,
        *,
        model: str = "gpt-5.6-luna",
        client: Any | None = None,
        max_output_tokens: int = 600,
    ) -> None:
        self.provider = OpenAIResponsesProvider(
            backend=LLMBackend.OPENAI_LUNA,
            model=model,
            client=client,
        )
        self.max_output_tokens = max_output_tokens

    def checkpoint(self, run_number: int, progress: list[SlotProgress]) -> str:
        evidence = [item.model_dump_json() for item in progress]
        return self._respond(
            "Кратко объясни контрольное решение GrindLess на русском. "
            "Не пересчитывай метрики и не прогнозируй результат улучшения предметов. "
            f"Прогон: {run_number}. Данные сессии: " + "[" + ",".join(evidence) + "]"
        )

    def final(self, result_summary: dict[str, object]) -> str:
        return self._respond(
            "Кратко объясни финальное решение GrindLess на русском, строго по "
            "структурированному результату: "
            + json.dumps(result_summary, ensure_ascii=False, sort_keys=True)
        )

    def _respond(self, prompt: str) -> str:
        completion = self.provider.complete(
            LLMRequest(
                purpose="legacy_narrator",
                input_text=prompt,
                max_output_tokens=self.max_output_tokens,
            )
        )
        return completion.text
