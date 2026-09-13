# ADR 0020: Recover a stable Artiscan near-end scan

- Status: superseded by [ADR 0021](0021-stop-artiscan-through-the-active-modal.md)
- Date: 2026-09-09
- Supersedes: [ADR 0017](0017-observe-artiscan-webcodecs-canvas-and-progress.md)

## Context

Version 0.16.0 observed Artiscan's real WebCodecs canvas and progress bar, but
treated every non-black stream as naturally complete or generally stalled. A
real macOS run reached a populated catalogue and a stable displayed progress of
99%, then failed through the 90-second watchdog. The final sampled frame can be
below the trim endpoint, so 99% is a valid near-end state.

The former failure text also replaced the active phase with a generic failed
state, hiding whether scanning, stopping or export failed.

## Decision

1. Prefer Artiscan's natural completion and the sustained black-tail trigger.
2. Track progress, the downsampled canvas signature and positive catalogue
   count as independent activity signals.
3. When progress is at least 98.5%, at least one artifact is catalogued and all
   signals remain unchanged for ten seconds, classify `near_end_idle` and press
   the unique enabled scoped `Stop Scan` action once.
4. Below the threshold or with an empty catalogue, retain the 90-second
   fail-closed watchdog and eight-minute overall deadline.
5. After stopping, require one enabled `View Artifacts` and one enabled
   `Download JSON`; validate the downloaded GOOD before import.
6. Preserve the active phase and original error in every failure message.

## Consequences

- A valid final sampled frame no longer falls through to the general watchdog.
- The recovery is narrow: it cannot accept an empty or early stalled scan.
- Positive catalogue state permits a stop but never permits partial import.
- The real macOS fixture remains required for post-release E2E validation.
