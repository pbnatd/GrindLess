# ADR 0013: Run operator-assisted video import as a local job

- Status: accepted
- Date: 2026-09-09

## Context

The browser Artiscan adapter already converts a recording to validated GOOD,
but the graphical application only accepted the resulting JSON. This forced the
user to leave GrindLess, run a separate script, find an intermediate file and
upload it again. Video is the preferred product input and an observed macOS scan
takes several minutes plus two manual checkpoints, so a synchronous page request
is not a reliable application contract.

An uploaded recording is sensitive local data. A multipart endpoint on loopback
also needs an explicit browser-origin boundary because a foreign page may attempt
to submit a form to localhost even when it cannot read the response.

## Decision

Expose video as the primary inventory action in the local UI and keep direct
GOOD JSON as the fallback. The loopback API owns a single-user job contract:

- `POST /api/v1/video-imports` streams one supported video to a private temporary
  directory, requires `X-GrindLess-Local: 1`, returns `202` and a `job_id`;
- `GET /api/v1/video-imports/{job_id}` exposes `queued`, `scanning`, `succeeded`
  or `failed` together with an honest operator message;
- only one queued or running scan is accepted at a time;
- the worker launches the existing pinned, visible, offline-before-video
  `BrowserArtiscanExtractor` and does not reinterpret OCR output;
- success returns the validated GOOD payload to the same browser session, which
  immediately calls the existing inventory audit;
- failure never returns partial GOOD;
- the temporary video is deleted after either success or failure.

The current job registry and completed GOOD payload are process memory for the
one-computer prototype. They are not a durable multi-user queue. The persistent
Artiscan browser profile remains separate so compatible calibration can be
reused without retaining the recording.

## Consequences

- A user no longer handles `extracted.good.json` in the normal application flow.
- The required `No` and black-frame `Stop Scan` actions remain visible and are
  not misrepresented as automation.
- Upload size, extension, concurrent-scan and scanner failures stop visibly.
- A custom request header forces a cross-origin preflight; no CORS permission is
  granted, while the existing Host allowlist remains in force.
- The macOS application launcher installs Playwright Chromium as well as the
  local API dependencies.
- A server rollout must replace this in-memory one-user job owner with an
  authenticated queue and private object lifecycle; it must not expose this
  loopback contract unchanged.
