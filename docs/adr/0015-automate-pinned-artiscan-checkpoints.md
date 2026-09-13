# ADR 0015: Automate the pinned Artiscan checkpoints

- Status: accepted
- Date: 2026-09-09
- Supersedes: [ADR 0009](0009-keep-the-first-artiscan-flow-operator-assisted.md)
- Amends: [ADR 0013](0013-run-operator-assisted-video-import-as-a-local-job.md)

## Context

The evaluated video import required the operator to decline transcoding and to
press `Stop Scan` when the recording reached its black tail. Those interactions
made video a working input, but not a zero-click product input. The Artiscan
build is already pinned and a successful 108-item reference export exists, so
the two known UI transitions can now be automated without delegating them to an
LLM or guessing screen coordinates.

A fixed timer is unsafe because recording length and scan speed vary. Waiting
only for playback to end is also insufficient for recordings with a deliberate
black tail: Artiscan continues scanning until its stop control is pressed.
The 55.08-second reference recording itself ends on the iOS control overlay,
not on encoded black frames; its black scanner display therefore corresponds to
the media ending. The implementation supports both observations explicitly.

## Decision

The browser adapter owns a deterministic, fail-closed interaction state machine:

1. After assigning the local video, require the exact transcoding question and
   exactly one enabled `No` button, then click it.
2. Start the scan and sample the single decoded HTML video element into a small
   in-memory canvas. A stop candidate is a frame with at least 98% dark pixels
   and mean luminance at most 12, sustained for 500 ms after non-black content
   has already been observed and at least 80% of the media has elapsed.
3. If no black tail is present, the media element's actual end is the fallback
   stop trigger.
4. Require exactly one enabled `Stop Scan` button, click it, wait for the running
   state to end, and require a positive catalogued-artifact count before export.
5. Treat a missing or ambiguous prompt, multiple decoded videos, an unavailable
   stop control, timeout, zero artifacts, invalid GOOD, or changed pinned build
   as a failed import. Do not return a partial inventory.

The normal local application runs Chromium headlessly. The CLI retains
`--artiscan-headful` for observable evaluation and debugging. Extraction audit
records `interaction_mode=fully_automated`, both automated action identifiers,
and whether the stop trigger was `black_tail` or `video_ended`.

This browser adapter remains separate from every future `GameAdapter`.
Automating an offline Artiscan page does not grant permission to control or
inspect the Genshin process.

## Consequences

- Video import no longer requires the user to click inside Artiscan.
- Stop timing follows observed media state rather than recording-specific wall
  clock timing.
- The pinned selector and frame-detection contract is replaceable if an owned
  OCR adapter is added later.
- The existing 108-item reference must be rerun on macOS before the new flow is
  called regression-validated; unit tests prove orchestration, not OCR parity.
- Recordings containing a sustained near-black interval after real content may
  stop early. Such results remain subject to strict GOOD validation and, where
  a reference exists, content comparison.
