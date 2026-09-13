from __future__ import annotations

import unittest

from grindless.models import Slot, SlotProgress, Stat
from grindless.openai_narrator import OpenAINarrator


class _FakeResponse:
    output_text = "Остановиться: найден перспективный кандидат."


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse()


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


class OpenAINarratorTests(unittest.TestCase):
    def test_uses_responses_api_without_recalculating_the_decision(self) -> None:
        client = _FakeClient()
        narrator = OpenAINarrator(client=client)
        progress = SlotProgress(
            slot=Slot.PLUME,
            baseline_artifact_id="old",
            best_artifact_id="new",
            evaluation_mode="content_only",
            baseline_content_score=3,
            candidate_content_score=4,
            content_score_gain=1,
            matched_substats=[Stat.CRIT_RATE, Stat.CRIT_DMG],
            accepted=True,
            reason="content improved",
        )

        text = narrator.checkpoint(1, [progress])

        self.assertIn("перспективный", text)
        self.assertEqual(client.responses.calls[0]["model"], "gpt-5.6-luna")
        self.assertIn("не прогнозируй", client.responses.calls[0]["input"])


if __name__ == "__main__":
    unittest.main()
