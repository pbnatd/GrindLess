from __future__ import annotations

import argparse
import json

from .platform_support import PlatformSupport, platform_support


def _print_human(report: PlatformSupport) -> None:
    print(f"Host: {report.host.value} ({report.architecture})")
    for name in (
        "simulator",
        "good_import",
        "video_import",
        "local_qwen",
        "cloud_luna",
        "game_execution",
    ):
        item = getattr(report, name)
        print(f"{name}: {item.status.value} — {item.reason}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show the honest GrindLess capability matrix for this computer"
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()

    report = platform_support()
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return
    _print_human(report)


if __name__ == "__main__":
    main()
