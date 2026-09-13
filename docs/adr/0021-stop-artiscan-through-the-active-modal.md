# ADR 0021: Stop Artiscan through the active modal

- Status: accepted
- Date: 2026-09-09
- Supersedes: [ADR 0020](0020-recover-stable-artiscan-near-end-scan.md)

## Context

The first near-end recovery run reached `stopping`, but Playwright found two
buttons named `Stop Scan`. Artiscan keeps `Running Scan` mounted while an
`Artifact Correction` dialog handles an OCR error. Both dialogs expose a stop
action, but the upper correction modal owns current interaction.

## Decision

1. Never locate `Stop Scan` from the page root.
2. Require exactly one open `Running Scan` dialog.
3. If exactly one `Artifact Correction` dialog is open, use its unique enabled
   `Stop Scan`; otherwise use the unique enabled action inside `Running Scan`.
4. Multiple dialogs, missing controls and disabled controls fail closed.
5. Record `scan_stop_control` as `artifact_correction`, `running_scan` or null.

## Consequences

- The adapter handles the real two-dialog end state without guessing.
- Stop behavior follows the modal that owns user interaction.
- Near-end, black-tail, offline-network and strict-GOOD rules remain unchanged.
- A real macOS replay remains the final E2E regression check.
