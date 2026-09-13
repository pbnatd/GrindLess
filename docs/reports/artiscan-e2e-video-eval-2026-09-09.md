# Artiscan video E2E evaluation — macOS, 2026-09-09

## Outcome

The representative video completed the local macOS Artiscan path and produced
a strictly valid GOOD v1 document. All 108 artifacts exactly match the frozen
reference by gameplay-relevant content. The recognition gate passes for this
recording.

The browser adapter remains experimental: this is one recording and Artiscan is
an undocumented third-party UI. A second, instrumented run closes the first
runtime and peak-memory observation. The path is operator-assisted rather than
unattended.

## Inputs

- Source recording: `IMG_7646.MP4`, H.264/AAC, 1920 x 880, 55.081667 seconds.
- Reference: the user-supplied Artiscan GOOD v1 `artifacts.json`.
- Candidate: `extracted.good.json` produced by the committed macOS launcher.
- Both documents declare `source=Artiscan` and contain 108 five-star, level-zero
  Obsidian Codex artifacts.

## Comparison contract

Both files first pass the production GOOD importer. Comparison then uses a
multiset signature containing set, slot, rarity, level, main stat, all observed
substat keys and values, equipped location and lock state. Artifact order and
substat order are ignored. Numeric spelling is normalized. A missing location
is equivalent to `location=""`, and a missing lock flag is equivalent to
`lock=false`, matching the GOOD defaults used by the importer.

The committed command is:

```bash
grindless-good-compare artifacts.json extracted.good.json
```

## Results

| Check | Result |
|---|---:|
| Strict import | 108 / 108 in both files; zero warnings |
| Exact core artifacts, order-independent | 108 / 108 (100.0%) |
| Exact artifacts at the same sequence position | 108 / 108 (100.0%) |
| Set | 108 / 108 |
| Slot | 108 / 108 |
| Rarity and level | 108 / 108 |
| Main stat | 108 / 108 |
| Complete substat key/value collection | 108 / 108 |
| Equipped-location semantics | 108 / 108 |
| Lock state | 108 / 108 |
| Missing core records | 0 |
| Extra core records | 0 |

The only raw-JSON difference is benign: the reference omits `location` on all
108 unequipped artifacts, while the candidate writes `"location": ""` on all
108. The importer normalizes both to the same unequipped state.

## Browser and network audit

The launcher-produced `run-report.json` contains the extraction audit generated
in the same successful process:

| Invariant | Observed value |
|---|---:|
| Pinned Artiscan build | `2026-08-11 21:06:10` |
| Browser offline before video assignment | `true` |
| Exported and imported artifacts | 108 / 108 |
| Recorded requests | 87 |
| Same-origin requests | 87 |
| `GET` requests | 87 |
| Foreign-origin requests | 0 |
| Non-`GET` requests | 0 |
| WebSocket requests | 0 |

All 87 recorded requests use `https://artiscan.ninjabay.org` and are classified
as same-origin static `GET`. No request requiring a block was attempted. The
committed control flow loads the application under this policy and the audit
records the context-level offline switch before the file-input assignment. The
current report format does not attach a phase timestamp to every request.

This is application-level evidence, not an independent packet capture. It
demonstrates that the committed adapter reached and reported its security gate;
an external network capture would be a stronger optional defense-in-depth test.

The non-network report fields were recomputed from `extracted.good.json` with
the committed CLI and match exactly, including the empty-baseline Mavuika audit:
a starter five-slot build is available, while sands, goblet and circlet remain
pending goals.

## Required operator checkpoints

The successful macOS path contains three visible user actions that must not be
hidden in the product description:

1. On first launch, if Gatekeeper blocks the downloaded `.command` file, the
   user allows that specific launcher in **System Settings → Privacy &
   Security → Open Anyway**, confirms and launches it again.
2. In Artiscan's **“Would you like to transcode the video?”** prompt, the user
   chooses **No**.
3. When this recording reaches its black end frame after the final artifact,
   the user clicks **Stop Scan** once. Stopping while a card is visible risks an
   incomplete inventory.

Gatekeeper runs before the launcher and therefore cannot appear in its JSON
audit. Version 0.9.0 marks future extraction reports as
`interaction_mode=operator_assisted` and lists the two in-browser checkpoints.

## What this proves

- A user on macOS can run the local video-to-GOOD flow without Windows.
- For this recording, OCR completeness and every imported artifact field are
  exact against the reference.
- The generated file is accepted by the same strict importer used by the agent;
  no manual correction or partial-import exception is required.
- The pinned build and the offline-before-video security gate were reached, and
  every recorded request satisfied the same-origin `GET` policy.

## First performance observation

The user-supplied `run-report(1).json` from version 0.8.0 contains a complete
process-tree measurement:

| Metric | Observed value |
|---|---:|
| End-to-end wall time | 257.024 s (4 min 17.024 s) |
| Peak Python RSS | 51,052,544 bytes (48.7 MiB) |
| Peak Python + descendants RSS | 1,619,673,088 bytes (1,544.6 MiB) |
| Sampling interval | 100 ms |
| Successful samples | 2,281 |
| Measurement complete | `true`; zero warnings |
| Requests after offline video assignment | 0 recorded |

The process-tree figure includes the Playwright driver and Chromium renderer,
worker and utility processes. Summed RSS can double-count shared pages and may
miss sub-100-ms spikes. Wall time includes the user's response time at the
transcoding and end-of-scan checkpoints, so it is an operator-in-the-loop
latency result, not a benchmark of OCR compute alone.

P50/P95 still requires at least 30 preserved reports under a consistent
checkpoint procedure. Accuracy also needs a corpus of different resolutions,
scroll speeds and UI conditions before the extractor can leave experimental
status. Separate phase timestamps are needed before pure processing time can be
reported.

## Decision

Mark recognition and the adapter-level privacy gate successful for the 1920 x
880 fixture. Describe the current path as operator-assisted, keep it labeled
experimental until it passes a varied corpus and repeated operational
measurements, and keep direct GOOD JSON as the reliable fallback.
