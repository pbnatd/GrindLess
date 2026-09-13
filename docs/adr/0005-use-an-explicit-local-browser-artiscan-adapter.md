# ADR 0005: Use an explicit local-browser Artiscan adapter

- Status: accepted
- Date: 2026-09-08
- Supersedes: [ADR 0003](0003-normalize-video-and-json-to-good.md) only where it
  prohibits all Artiscan browser automation
- Amended by: [ADR 0009](0009-keep-the-first-artiscan-flow-operator-assisted.md)
  for the two current in-browser checkpoints

## Context

ADR 0003 correctly made validated GOOD the only inventory contract and rejected
an undocumented server API dependency. It also prohibited browser automation
because Artiscan's execution and privacy boundaries had not been inspected.

The subsequent passive audit found that the current Artiscan build is a static
PWA. It reads a selected video with `FileReader`, decodes frames with local
FFmpeg/WebAssembly workers, runs local Tesseract workers and creates the GOOD
download in the browser. Its normal scanner bundle contains no observed video
upload API. Therefore a local browser adapter can remove manual website steps
without sending the video to an Artiscan backend.

The Artiscan page and DOM are still undocumented third-party interfaces. The
adapter must not silently become an indispensable or trusted owner of inventory
truth.

## Decision

Add an explicitly selected experimental `BrowserArtiscanExtractor` behind the
existing `VideoInventoryExtractor` port. Direct GOOD JSON remains the reliable
fallback, and a future owned OCR implementation can replace the browser adapter
without changing import, optimization or stop-policy code.

The adapter follows this order:

1. start a persistent Chromium profile on the user's computer;
2. allow only same-origin static `GET` requests while Artiscan boots;
3. verify the pinned Artiscan build identifier;
4. switch the entire browser context offline;
5. only then assign the local video to Artiscan's file input;
6. reuse a compatible saved calibration or attempt Artiscan's own auto-detect;
7. run the scan and capture the locally generated GOOD download;
8. pass the untrusted document through the existing strict GOOD importer.

All requests and policy decisions are recorded in an extraction audit. A
non-GET request, another origin, an unexpected build, failed calibration,
invalid export, zero detected artifacts or a changed UI contract fails loud.
The adapter never falls back to an unpinned build or partial inventory.

Playwright is an optional dependency. Importing JSON and running the simulator
must not require a browser installation.

## Consequences

- A user can eventually provide one video instead of manually operating
  Artiscan and transferring JSON.
- The video is assigned only after the browser is offline, making the privacy
  boundary testable rather than inferred from the current third-party code.
- The first supported video resolution may require one visible calibration;
  compatible later videos reuse the persistent local profile.
- Artiscan UI and build changes cause a safe failure and require an adapter
  update.
- Redistribution or copying of Artiscan code is not authorized by this
  decision. The adapter loads the public application; an offline mirror needs
  a separate license decision.
- End-to-end recognition quality remains unverified until a representative
  source video is supplied.
