from __future__ import annotations

import argparse
import json
from pathlib import Path

from .application import analyze_mavuika_inventory
from .artiscan_browser import ArtiscanBrowserConfig, BrowserArtiscanExtractor
from .inventory_input import VIDEO_SUFFIXES, load_inventory_input
from .models import FarmPolicy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and inspect a GOOD-compatible inventory export"
    )
    parser.add_argument(
        "file",
        help="Path to Artiscan/GOOD JSON; video needs a configured extractor adapter",
    )
    parser.add_argument(
        "--character",
        help="Also require a complete five-artifact equipped build for this character key",
    )
    parser.add_argument(
        "--preset",
        choices=["mavuika"],
        help="Audit an unequipped character using a content-only build preset",
    )
    parser.add_argument("--top", type=int, default=5, help="Candidates per slot")
    parser.add_argument(
        "--artiscan-browser",
        action="store_true",
        help="Use the experimental local-browser Artiscan extractor for video input",
    )
    parser.add_argument(
        "--artiscan-headful",
        action="store_true",
        help="Show the otherwise automatic Artiscan flow for debugging",
    )
    parser.add_argument(
        "--artiscan-profile",
        type=Path,
        help="Persistent Chromium profile used to reuse compatible calibration",
    )
    parser.add_argument(
        "--artiscan-timeout-minutes",
        type=float,
        default=8,
        help="Maximum video extraction time (default: 8)",
    )
    parser.add_argument(
        "--save-extracted-good",
        type=Path,
        help="Save the validated raw GOOD export when browser video extraction succeeds",
    )
    args = parser.parse_args()

    input_suffix = Path(args.file).suffix.lower()
    if args.artiscan_browser and input_suffix not in VIDEO_SUFFIXES:
        parser.error("--artiscan-browser is only valid for video input")
    if args.save_extracted_good is not None and not args.artiscan_browser:
        parser.error("--save-extracted-good requires --artiscan-browser")
    if args.artiscan_timeout_minutes <= 0:
        parser.error("--artiscan-timeout-minutes must be positive")

    extractor = None
    if args.artiscan_browser:
        profile = args.artiscan_profile or (
            Path.home() / ".grindless" / "artiscan-browser"
        )
        extractor = BrowserArtiscanExtractor(
            ArtiscanBrowserConfig(
                headless=not args.artiscan_headful,
                profile_directory=profile,
                timeout_ms=int(args.artiscan_timeout_minutes * 60 * 1000),
            )
        )

    inventory = load_inventory_input(args.file, video_extractor=extractor)
    if args.save_extracted_good is not None:
        if extractor is None or extractor.last_good is None:
            raise RuntimeError("validated Artiscan GOOD payload is unavailable")
        output_path = args.save_extracted_good.expanduser().resolve()
        if output_path == Path(args.file).expanduser().resolve():
            parser.error("--save-extracted-good must not overwrite the input video")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(extractor.last_good, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    result = inventory.report.model_dump(mode="json")
    if extractor is not None and extractor.last_audit is not None:
        result["video_extraction"] = extractor.last_audit.as_dict()
    if args.character:
        state = inventory.to_account_state(args.character)
        result["selected_character"] = args.character
        result["equipped_artifact_ids"] = {
            slot.value: artifact_id
            for slot, artifact_id in state.character.equipped_artifact_ids.items()
        }
    if args.preset == "mavuika":
        if extractor is not None and extractor.last_good is not None:
            preset_payload = extractor.last_good
        else:
            preset_payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        analysis = analyze_mavuika_inventory(
            preset_payload,
            policy=FarmPolicy.ECONOMY,
            top_per_slot=args.top,
        )
        result["preset"] = analysis.preset.model_dump(mode="json")
        result["profile_evidence"] = analysis.profile_evidence.model_dump(mode="json")
        result["initial_build_audit"] = analysis.audit.model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
