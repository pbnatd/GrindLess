from __future__ import annotations

import argparse
import json
from pathlib import Path

from .linux_game_adapter import (
    LinuxGameReadiness,
    LinuxGameStatus,
    LinuxX11GameControl,
    probe_linux_game,
)
from .linux_game_observer import (
    DEFAULT_REFERENCE_DIRECTORY,
    DEFAULT_SHADOW_RUN_DIRECTORY,
    CalibratedScreenClassifier,
    GameScreenState,
    RECORDABLE_STATES,
    ScreenReferenceStore,
    ShadowEvidenceWriter,
    ShadowGameObserver,
)


def _print_human(readiness: LinuxGameReadiness) -> None:
    print(f"Status: {readiness.status.value}")
    print(f"Session: {readiness.session_type}; DISPLAY={readiness.display or 'missing'}")
    for check in readiness.checks:
        marker = "OK" if check.ok else ("BLOCK" if check.required else "NOTE")
        print(f"[{marker}] {check.message}")
    print(f"Next: {readiness.next_action}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe the Linux/X11 Genshin control boundary without guessing"
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--capture",
        type=Path,
        help="capture the verified game window to a PNG without sending input",
    )
    parser.add_argument(
        "--click",
        nargs=2,
        type=int,
        metavar=("X", "Y"),
        help="supervised relative click; also requires GRINDLESS_ENABLE_GAME_INPUT=1",
    )
    parser.add_argument(
        "--press",
        help="supervised allowlisted key press; also requires GRINDLESS_ENABLE_GAME_INPUT=1",
    )
    parser.add_argument(
        "--record-state",
        choices=[state.value for state in RECORDABLE_STATES],
        help="capture a trusted reference for a user-confirmed game state; sends no input",
    )
    parser.add_argument(
        "--observe-state",
        action="store_true",
        help="classify one capture from calibrated references; sends no input",
    )
    parser.add_argument(
        "--shadow-run",
        action="store_true",
        help="observe a complete route until reward or a fail-closed stop; sends no input",
    )
    parser.add_argument(
        "--reference-directory",
        type=Path,
        default=DEFAULT_REFERENCE_DIRECTORY,
        help="directory containing local state-reference captures",
    )
    parser.add_argument(
        "--note",
        default="",
        help="operator note stored with --record-state evidence",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="seconds between captures in --shadow-run",
    )
    parser.add_argument(
        "--shadow-directory",
        type=Path,
        default=DEFAULT_SHADOW_RUN_DIRECTORY,
        help="local directory for shadow-run frames and result JSON",
    )
    args = parser.parse_args()

    observation_modes = sum(
        bool(value) for value in (args.record_state, args.observe_state, args.shadow_run)
    )
    if observation_modes > 1:
        parser.error("choose only one of --record-state, --observe-state or --shadow-run")
    if observation_modes and (args.click or args.press):
        parser.error("state observation cannot be combined with mouse or keyboard input")

    readiness = probe_linux_game()
    if args.json:
        print(json.dumps(readiness.as_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human(readiness)

    if not (
        args.capture
        or args.click
        or args.press
        or args.record_state
        or args.observe_state
        or args.shadow_run
    ):
        return
    if readiness.status is not LinuxGameStatus.READY:
        raise SystemExit(f"Game adapter is not ready: {readiness.status.value}")

    control = LinuxX11GameControl(readiness)
    store = ScreenReferenceStore(args.reference_directory)
    if args.capture:
        payload = control.capture_png()
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        args.capture.write_bytes(payload)
        print(f"Captured verified game window: {args.capture}")
    if args.click:
        control.click(*args.click)
        print(f"Sent supervised click at {args.click[0]},{args.click[1]}")
    if args.press:
        control.press(args.press)
        print(f"Sent supervised key: {args.press}")
    if args.record_state:
        reference = store.record(
            GameScreenState(args.record_state),
            control.capture_png(),
            note=args.note,
        )
        print(json.dumps(reference.as_dict(), ensure_ascii=False, indent=2))
    if args.observe_state:
        observation = CalibratedScreenClassifier(store).classify(control.capture_png())
        print(json.dumps(observation.as_dict(), ensure_ascii=False, indent=2))
        if not observation.confirmed:
            raise SystemExit(2)
    if args.shadow_run:
        evidence = ShadowEvidenceWriter(args.shadow_directory)
        observer = ShadowGameObserver(
            control.capture_png,
            CalibratedScreenClassifier(store),
            stop_requested=control.stop_file.exists,
            evidence_sink=evidence.record,
        )
        result = observer.run(interval_seconds=args.interval)
        result_path = evidence.finish(result)
        payload = result.as_dict()
        payload["evidence_directory"] = str(evidence.directory)
        payload["result_path"] = str(result_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if result.outcome.value != "reward_observed":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
