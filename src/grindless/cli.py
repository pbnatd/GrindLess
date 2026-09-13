from __future__ import annotations

import argparse
import json

from .agent import GrindLessAgent
from .fixtures import xiangling_account, xiangling_goal
from .good_import import load_good
from .models import FarmPolicy
from .narrator import TemplateNarrator
from .openai_narrator import OpenAINarrator
from .simulator import ArtifactDomainSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GrindLess artifact simulator")
    parser.add_argument(
        "--policy",
        choices=[item.value for item in FarmPolicy],
        default=FarmPolicy.ECONOMY.value,
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resin", type=int, default=200)
    parser.add_argument("--good", help="use artifacts from a GOOD JSON export")
    parser.add_argument(
        "--character",
        default="Xiangling",
        help="GOOD character key; the MVP currently has a Xiangling goal preset",
    )
    parser.add_argument("--json", action="store_true", help="print the complete result as JSON")
    parser.add_argument(
        "--narrator",
        choices=["template", "openai"],
        default="template",
        help="offline template or OpenAI Responses API explanations",
    )
    parser.add_argument("--model", default="gpt-5.6-luna")
    args = parser.parse_args()

    policy = FarmPolicy(args.policy)
    if args.character != "Xiangling":
        parser.error("the simulator MVP currently supports the Xiangling goal preset")
    state = xiangling_account()
    import_report = None
    if args.good:
        inventory = load_good(args.good)
        state = inventory.to_account_state(args.character)
        import_report = inventory.report
    narrator = (
        OpenAINarrator(model=args.model)
        if args.narrator == "openai"
        else TemplateNarrator()
    )
    result = GrindLessAgent(narrator=narrator).run(
        state=state,
        goal=xiangling_goal(policy),
        adapter=ArtifactDomainSimulator(seed=args.seed, resin=args.resin),
    )
    if args.json:
        payload = {"session": result.model_dump(mode="json")}
        if import_report is not None:
            payload["good_import"] = import_report.model_dump(mode="json")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if import_report is not None:
        print(
            f"GOOD: импортировано артефактов — {import_report.artifacts_imported}; "
            f"источник — {import_report.source}."
        )
    print(result.recommendation)
    print(f"Осталось смолы: {result.resin_remaining}")
    print(f"Контрольных модельных точек: {result.model_checkpoints}")
    for item in result.slot_progress:
        mark = "✓" if item.accepted else "·"
        print(f"{mark} {item.slot.value}: {item.reason}")
