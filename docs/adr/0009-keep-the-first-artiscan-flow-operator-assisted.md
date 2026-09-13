# ADR 0009: Keep the first Artiscan flow operator-assisted

- Status: accepted
- Date: 2026-09-09
- Amends: [ADR 0005](0005-use-an-explicit-local-browser-artiscan-adapter.md),
  which incorrectly implied that all website interaction was already automated

## Context

The first real macOS runs exposed three user-visible gates. Gatekeeper may block
the downloaded launcher before it starts. After the adapter assigns the video,
Artiscan asks whether to transcode it. At the black tail of the supported
recording, Artiscan keeps scanning until the user presses `Stop Scan`.

Pretending these steps are autonomous would make the CLI hang in hidden mode,
misstate the product's maturity and obscure human response time inside the
runtime metric. Automatically clicking an undocumented prompt or inferring the
last useful frame without a regression corpus could also truncate the
inventory.

## Decision

The first Artiscan video flow is explicitly `operator_assisted`:

1. If macOS blocks the launcher, allow only that file through **System Settings
   → Privacy & Security → Open Anyway**, then start it again. Never instruct the
   user to disable Gatekeeper globally.
2. Run Chromium visibly and choose **No** in **“Would you like to transcode the
   video?”**.
3. Click **Stop Scan** only when the supported recording reaches the black end
   frame after the final artifact.

The production CLI rejects `--artiscan-browser` without
`--artiscan-headful`. Future extraction audits declare the interaction mode and
the two in-browser checkpoint identifiers. The macOS approval cannot be logged
by the process because it occurs before launch, so it is preserved in a
dedicated runbook.

The measured wall clock intentionally spans the operator checkpoints. It is
reported as end-to-end operator-assisted latency. Pure OCR or system processing
latency requires separate phase timestamps.

## Consequences

- The MVP is honest and usable on macOS, but it is not yet a zero-click video
  importer.
- A user can see exactly when intervention is required and avoids unnecessary
  transcoding for the tested source.
- A premature `Stop Scan` can yield a partial inventory. For the fixture, the
  content comparator detects this against the frozen 108-item reference; a
  general production scan still needs an explicit coverage confirmation.
- Automating either checkpoint requires selectors/end-of-video detection, a
  varied regression corpus and a later decision that supersedes this one.
