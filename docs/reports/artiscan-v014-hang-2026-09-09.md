# Artiscan v0.14.0 hang investigation — 2026-09-09

## Outcome

Version 0.14.0 cannot automatically detect the end of an uploaded Artiscan
video. The reported five-minute `Artiscan работает` state is a product defect,
not a user action that was still pending.

## Evidence

- The v0.14.0 end predicate selects `document.querySelectorAll('video')` and
  returns no terminal state unless exactly one decoded video is present.
- The pinned Artiscan build is still `2026-08-11 21:06:10`.
- Its uploaded-file implementation demuxes the file and decodes frames with
  WebCodecs. The running scan renders `ImageData` through a canvas component;
  it does not mount an HTML video element for that source.
- The running modal exposes a `Stop Scan` button and a progress component whose
  inline width represents remaining source progress.
- v0.14.0 reports only the broad job status `scanning`. Its browser deadline is
  15 minutes and it has no no-progress watchdog, so the UI cannot distinguish
  active OCR from the impossible end predicate.
- The preserved fixture is `IMG_7646.MP4`: H.264, 1920 × 880, 55.081667 seconds.
  Its earlier operator-assisted run produced 108/108 exact artifacts in 257.024
  seconds. That earlier result validates OCR content, not the new automation.

## Fix after triage

- Replace HTML-video observation with the current-frame canvas plus modal
  progress.
- Treat black tail and Artiscan's natural finite-stream completion as distinct
  terminal states.
- Record only UI actions that actually occurred.
- Expose `phase`, `updated_at` and `progress` through the local job API and UI.
- Add an activity watchdog and an eight-minute overall deadline. The first
  proposal used 90 seconds; the accepted follow-up configuration is 10 seconds.
- Add regression tests that reject any return to an HTML-video selector and
  cover black-tail stop, natural completion and stalled-scan failure.

## Verification boundary

Static inspection of the pinned Artiscan implementation and automated tests
verify the corrected contract and state machine. The current environment could
not download Playwright Chromium, so the 108-item fixture must be rerun on macOS
before recording an end-to-end pass for version 0.16.0.
