# ADR 0017: Observe Artiscan WebCodecs canvas and progress

- Status: superseded by [ADR 0020](0020-recover-stable-artiscan-near-end-scan.md)
- Date: 2026-09-09
- Supersedes: [ADR 0015](0015-automate-pinned-artiscan-checkpoints.md)

## Context

ADR 0015 assumed that Artiscan rendered an uploaded file through one decoded
HTML `video` element. Version 0.14.0 implemented that assumption literally.
During a real application run, the UI remained in `scanning` because the
end-state predicate always saw zero matching video elements and could wait for
the full 15-minute deadline.

Inspection of the pinned Artiscan build `2026-08-11 21:06:10` shows a different
contract. Uploaded files are demuxed and decoded through WebCodecs. The running
modal receives `ImageData`, renders its current frame on a `canvas`, and exposes
source position through a remaining-progress bar. The finite stream may also
complete naturally and close the running modal.

## Decision

1. Scope observation to the open dialog whose title is `Running Scan` and
   require exactly one `Stop Scan` action in that dialog.
2. Observe the largest visible canvas in that dialog, not a nonexistent HTML
   video element. Downsample it in memory for black-tail and activity checks.
3. Read the dialog's single percentage-width progress indicator for status and
   activity checks. Click `Stop Scan` only for the sustained near-black tail
   trigger after 80% progress; do not abort a final non-black frame while OCR is
   still processing it.
4. Accept Artiscan's own natural finite-stream completion when the running
   dialog closes and a positive catalogue count is visible. Do not claim a stop
   click in the audit when no click occurred.
5. Publish the current phase, last update and progress to the local job. Fail
   after 10 seconds without canvas/progress activity or eight minutes overall.
6. Continue to reject ambiguous controls, zero artifacts, invalid GOOD and
   changed pinned builds without returning a partial inventory.

## Consequences

- The automatic flow follows Artiscan's real rendering contract and can reach
  its stop/export states for uploaded videos.
- A stalled scanner becomes an explicit error instead of a long generic wait.
- Canvas/progress selectors remain coupled to the pinned third-party UI and
  therefore stay behind the replaceable `ArtiscanAdapter` boundary.
- The 108-item macOS reference still requires a real post-fix run before the
  new automatic path can be called end-to-end regression-validated.
