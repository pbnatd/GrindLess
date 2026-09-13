# Artiscan v0.16.0 near-end stall — 2026-09-09

## Outcome

The real macOS scan reached a populated catalogue and displayed 99%, then
failed. This was a state-machine defect, not evidence of bad OCR: v0.16.0 never
classified a stable final sampled frame as a recoverable end state.

## Implemented correction

- `near_end_idle` activates only after ten seconds at progress at least 98.5%,
  with a positive catalogue and no frame, progress or catalogue change.
- A non-final stall retains the 90-second watchdog.
- The stop action is scoped to Artifact Correction when present, otherwise to
  Running Scan; the owning modal is recorded in `scan_stop_control`.
- Export requires unique enabled catalogue and download controls.
- Worker errors preserve the failed phase and original cause.

## Verification boundary

Automated tests cover both stop-dialog paths, the near-end predicate, timeout
ordering, GOOD validation and error evidence. A real macOS replay remains
required before calling the complete video route E2E regression-validated.
