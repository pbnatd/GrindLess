from __future__ import annotations

from .models import SlotProgress


class TemplateNarrator:
    """Offline stand-in for Qwen/Luna using the final structured contract."""

    def checkpoint(self, run_number: int, progress: list[SlotProgress]) -> str:
        accepted = [item.slot.value for item in progress if item.accepted]
        pending = [item.slot.value for item in progress if not item.accepted]
        return f"run={run_number}; accepted={accepted}; pending={pending}"

    def final(self, result_summary: dict[str, object]) -> str:
        decision = result_summary["decision"]
        reason = result_summary["reason"]
        runs = result_summary["runs"]
        spent = result_summary["resin_spent"]
        return f"{decision}. {reason} За {runs} прогонов потрачено {spent} смолы."
