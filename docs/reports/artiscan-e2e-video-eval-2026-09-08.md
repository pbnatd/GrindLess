# Artiscan video E2E evaluation attempt — 2026-09-08

> Superseded for recognition accuracy by the successful local macOS run on
> 2026-09-09. See
> [the completed comparison](artiscan-e2e-video-eval-2026-09-09.md). This record
> is retained to distinguish infrastructure failure from OCR failure.

## Outcome

The representative source video was received and is suitable for an Artiscan
recognition test, but this environment could not complete the browser run. No
GOOD export was produced, so recognition accuracy, completeness and runtime are
still unmeasured. The browser extractor must remain experimental.

## Evidence collected

- Source: `IMG_7646.MP4` supplied by the user together with the known Artiscan
  export `artifacts.json` containing 108 artifacts.
- Container: H.264 video with AAC audio.
- Resolution: 1920 x 880.
- Duration: 55.081667 seconds.
- Size: 43,852,836 bytes.
- Average frame rate: approximately 31.1 fps.
- Sampled frames show the English Genshin artifact inventory and a readable,
  unobstructed detail panel. The recording progresses through flower, plume,
  sands, goblet and circlet inventory regions.
- Three sampled cards were found exactly in the 108-item reference export: the
  opening Obsidian Codex flower, a mid-video Obsidian Codex plume and a late
  Obsidian Codex HP% circlet. The circlet's grey `DEF+21 (unactivated)` line is
  correctly absent from GOOD substats. This verifies that the video and JSON
  belong to the same capture sequence at sampled points; it is not an OCR
  accuracy measurement.
- The visible Artiscan build still reports `2026-08-11 21:06:10`, matching the
  adapter pin.

## Privacy handling

The recording contains a visible account UID. For the cloud-browser-only
diagnostic, a temporary copy was created with the UID covered and audio removed.
The artifact detail panel was not modified. The production adapter is still
required to assign the original video only after its local browser context is
offline.

## Failed execution paths

### Local Playwright run

The Python package and project dependencies installed in an isolated temporary
environment. The Chromium runtime was not present. Its download from
`cdn.playwright.dev` timed out under the container's network policy, so the
local adapter could not start a browser.

### Cloud-browser functional run

Artiscan loaded and exposed the expected `Video File` control. Transfer of the
9.9 MB redacted copy to the supported cloud browser did not complete and the
attempt was cancelled. No scan started and no JSON download appeared. This path
also cannot exercise the adapter's context-level offline switch, so it is not a
substitute for the local security test.

## Interpretation

The failures occurred before Artiscan received a confirmed usable source and do
not measure OCR quality. They neither validate nor falsify the adapter. Partial
inventory must not be inferred from sampled frames or the existing reference
JSON.

## Required next run

Run the committed `BrowserArtiscanExtractor` on the user's macOS machine with
locally installed Playwright Chromium and access to Artiscan's static assets.
The extraction path is desktop-portable and does not require Windows. Preserve
the extractor audit and compare the downloaded GOOD document with the frozen
108-artifact reference. The acceptance record must include:

1. pinned build verification;
2. confirmation that the context was offline before video assignment;
3. complete request-policy audit;
4. detected artifact count;
5. exact and field-level comparison with the reference GOOD export;
6. wall-clock time and peak memory;
7. any calibration or OCR correction required.

Until that run succeeds, direct GOOD JSON remains the reliable input path.
