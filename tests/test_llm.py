from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from grindless.llm import (
    AuditedNarrator,
    LLMBackend,
    LLMCompletion,
    LLMRequest,
    OpenAIResponsesProvider,
    ReasoningEffort,
    SQLiteQuotaStore,
)
from grindless.models import Slot, SlotProgress, Stat


class _Provider:
    backend = LLMBackend.OPENAI_LUNA
    model = "test-model"

    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMCompletion:
        self.requests.append(request)
        if self.fails:
            raise RuntimeError("synthetic provider failure")
        return LLMCompletion(
            text="Проверка объяснена.",
            input_tokens=123,
            output_tokens=17,
            response_id="resp_test",
        )


class _ResponsesAPI:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        output = []
        if kwargs.get("tools"):
            output = [
                {
                    "type": "web_search_call",
                    "action": {
                        "sources": [
                            {"url": "https://example.com/guide", "title": "Current guide"}
                        ]
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/mechanics",
                                    "title": "Mechanics reference",
                                }
                            ],
                        }
                    ],
                },
            ]
        return type(
            "Response",
            (),
            {
                "output_text": '{"answer":"ok"}',
                "usage": {"input_tokens": 12, "output_tokens": 5},
                "id": "resp_structured",
                "output": output,
            },
        )()


class _ResponsesClient:
    def __init__(self) -> None:
        self.responses = _ResponsesAPI()


def progress() -> list[SlotProgress]:
    return [
        SlotProgress(
            slot=Slot.SANDS,
            baseline_artifact_id="old",
            best_artifact_id="new",
            evaluation_mode="content_only",
            baseline_content_score=2,
            candidate_content_score=4,
            content_score_gain=2,
            matched_substats=[Stat.CRIT_RATE, Stat.CRIT_DMG],
            accepted=True,
            reason="content improved",
        )
    ]


class AuditedNarratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / "state.sqlite3"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_success_is_metered_and_audited(self) -> None:
        provider = _Provider()
        quota = SQLiteQuotaStore(self.database, daily_limit=2, monthly_limit=3)
        narrator = AuditedNarrator(
            provider,
            quota,
            input_usd_per_million=2.0,
            output_usd_per_million=8.0,
        )

        text = narrator.checkpoint(1, progress())
        report = narrator.report()

        self.assertEqual(text, "Проверка объяснена.")
        self.assertTrue(report.external_data_sent)
        self.assertEqual(report.successful_calls, 1)
        self.assertTrue(report.calls[0].provider_called)
        self.assertIn('"slot": "sands"', report.calls[0].transmitted_text)
        self.assertEqual(report.calls[0].response_id, "resp_test")
        self.assertEqual(report.total_input_tokens, 123)
        self.assertEqual(report.total_output_tokens, 17)
        self.assertEqual(report.total_tokens, 140)
        self.assertAlmostEqual(report.estimated_cost_usd or 0, 0.000382)
        self.assertEqual(quota.snapshot().input_tokens_this_month, 123)

    def test_provider_failure_uses_template_and_records_transmission(self) -> None:
        provider = _Provider(fails=True)
        quota = SQLiteQuotaStore(self.database)
        narrator = AuditedNarrator(provider, quota)

        text = narrator.checkpoint(1, progress())
        report = narrator.report()

        self.assertTrue(text)
        self.assertEqual(report.status, "degraded")
        self.assertTrue(report.external_data_sent)
        self.assertTrue(report.calls[0].provider_called)
        self.assertIn("synthetic provider failure", report.calls[0].error or "")
        self.assertEqual(quota.snapshot().used_today, 0)
        self.assertEqual(quota.snapshot().attempts_today, 1)

    def test_quota_rejection_never_calls_provider(self) -> None:
        provider = _Provider()
        quota = SQLiteQuotaStore(self.database, daily_limit=0, monthly_limit=0)
        narrator = AuditedNarrator(provider, quota)

        narrator.checkpoint(1, progress())
        report = narrator.report()

        self.assertEqual(provider.requests, [])
        self.assertFalse(report.external_data_sent)
        self.assertFalse(report.calls[0].provider_called)
        self.assertIn("limit", report.calls[0].error or "")

    def test_openai_strategy_request_uses_json_schema_output(self) -> None:
        client = _ResponsesClient()
        provider = OpenAIResponsesProvider(
            backend=LLMBackend.OPENAI_LUNA,
            model="test-model",
            client=client,
        )

        completion = provider.complete(
            LLMRequest(
                purpose="strategy",
                input_text="Return JSON",
                max_output_tokens=4_000,
                response_schema={
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
                response_schema_name="strategy_output",
            )
        )

        call = client.responses.calls[0]
        self.assertEqual(completion.text, '{"answer":"ok"}')
        self.assertEqual(call["max_output_tokens"], 4_000)
        self.assertEqual(
            call["text"],
            {
                "format": {
                    "type": "json_schema",
                    "name": "strategy_output",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                    },
                    "strict": False,
                }
            },
        )

    def test_openai_strategy_requires_web_search_and_records_sources(self) -> None:
        client = _ResponsesClient()
        provider = OpenAIResponsesProvider(
            backend=LLMBackend.OPENAI_SOL,
            model="gpt-5.6-sol",
            client=client,
        )

        completion = provider.complete(
            LLMRequest(
                purpose="strategy",
                input_text="Research and return JSON",
                reasoning_effort=ReasoningEffort.HIGH,
                web_search=True,
            )
        )

        call = client.responses.calls[0]
        self.assertEqual(call["reasoning"], {"effort": "high"})
        self.assertEqual(call["tools"], [{"type": "web_search"}])
        self.assertEqual(call["tool_choice"], "required")
        self.assertEqual(call["include"], ["web_search_call.action.sources"])
        self.assertTrue(completion.web_search_used)
        self.assertEqual(
            {source.url for source in completion.web_sources},
            {"https://example.com/guide", "https://example.com/mechanics"},
        )


if __name__ == "__main__":
    unittest.main()
