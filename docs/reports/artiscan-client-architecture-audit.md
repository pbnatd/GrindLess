# Artiscan client architecture audit

- Date: 2026-09-08
- Scope: passive inspection of the public Artiscan web application
- Site: <https://artiscan.ninjabay.org/>
- Observed build: `2026-08-11 21:06:10`

## Question

Can GrindLess send an inventory video directly to an Artiscan backend and
receive GOOD JSON without requiring the user to operate the website?

## Evidence

### The normal scanner is browser-local

The public UI explicitly says that Artiscan processes a recorded video
"straight from within your browser". Its artifact route exposes a hidden
`input[type=file][accept="video/*"]`, screen capture and screenshot sources.

The current static manifest includes all heavy processing assets in the web
application itself:

- `/ffmpeg/ffmpeg.js` and `/ffmpeg/ffmpeg.wasm`;
- `/assets/worker.min-DRmt-Jn5.js`;
- four Tesseract WASM loaders under `/tesseract/`;
- `/tesseract/genshin_fast_09_04_21.traineddata.gz`.

The main bundle reads the selected file with `FileReader.readAsArrayBuffer`,
loads it into an FFmpeg worker, decodes frames and runs Tesseract workers whose
`corePath`, `workerPath` and `langPath` point to same-origin static assets.

### No video-upload API is used by this build

The public loader, main bundle and service worker were searched for network
primitives and endpoint markers. The application bundle contains no
`FormData`, `XMLHttpRequest`, `WebSocket`, `sendBeacon` or `/api` occurrence.
Its only `fetch` occurrence is inside a generic Tesseract input helper for
loading a resource URL. The remaining fetches belong to module preloading,
the update manifest, cache population and the service worker's cache fallback.

This does not prove that the site owner operates no private service. It does
show that the inspected public scanner does not send the selected video to one
during its normal flow, so there is no observed request contract for GrindLess
to call directly.

### GOOD JSON is assembled and downloaded in the browser

The main bundle constructs:

```json
{
  "format": "GOOD",
  "source": "Artiscan",
  "version": 1,
  "artifacts": []
}
```

It serializes that object with `JSON.stringify`, either writes it to the
clipboard or creates an `application/json` `Blob` and triggers a download named
`artifacts.json`. No server response produces the export.

### Observed deployment controls

The sampled root page and JavaScript bundle are served as static files by
nginx. They require no login, cookie or API token. The service worker uses a
SHA-256 manifest to refresh and cache static assets; this is an integrity and
offline-update mechanism, not an upload authorization mechanism. The sampled
responses did not advertise a cross-origin API.

There was no CAPTCHA or anti-automation screen in the normal scanner flow.
This is not a guarantee that future builds will behave identically.

## Conclusion

There is no useful "direct Artiscan backend" path in the inspected build.
Removing manual website interaction is still feasible, but the integration
must execute browser-local scanner code or replace it with our own local
extractor.

## Implementation options

| Option | Mechanism | Advantages | Main risks |
|---|---|---|---|
| Browser adapter | A local Chromium/WebView opens Artiscan, assigns the video to the file input, waits for scanning and captures the generated JSON blob | Fastest proof of concept; uses current recognition behavior; video need not leave the PC | Fragile DOM automation; third-party updates; availability; no documented programmatic contract |
| Local mirror of Artiscan | Run a downloaded copy of the static PWA on localhost | No dependency on website uptime after installation | Redistribution and license are not established; updates and provenance become our responsibility |
| Native GrindLess extractor | Decode frames locally and implement the crop, deduplication, OCR and GOOD conversion behind `VideoInventoryExtractor` | Stable owned interface; testable; no third-party UI automation | Most implementation and dataset work |
| Owner-supported integration | Ask the Artiscan author for source, license or a supported library/CLI contract | Potentially combines speed and maintainability | Depends on an external response and project policy |

## Recommended next experiment

Implement a disposable `BrowserArtiscanExtractor` proof of concept behind the
existing `VideoInventoryExtractor` port. It must run on the user's computer,
remain disabled unless explicitly selected, and fail loudly when the observed
build or UI contract changes.

During the experiment, record all browser requests and enforce a network
allowlist: static `GET` requests to the Artiscan origin only; block uploads,
beacons, WebSockets and non-GET requests. The test passes only if the produced
JSON validates as GOOD and no video bytes leave the local browser process.

Do not import or redistribute the minified bundle as a GrindLess dependency
until the Artiscan license or author permission is established. If the browser
adapter works, use it only as a baseline while the owned local extractor is
implemented and evaluated against the same videos.

## Implemented after triage

Version 0.5.0 adds the experimental adapter behind the existing video extractor
port. It pins the audited build, enforces same-origin GET-only bootstrap,
switches the context offline before assigning the video, attempts Artiscan's
own scan-zone auto-detection, captures the JSON download and leaves validation
to the existing GOOD importer. Direct JSON remains the fallback.

Unit tests cover the boundary, empty-export failure and network policy. A
representative source video has since been received, but an end-to-end
recognition result is still intentionally not claimed: the available container
could not start local Chromium, and the cloud-browser diagnostic stopped before
scanning. See
[the dated E2E attempt](artiscan-e2e-video-eval-2026-09-08.md) for evidence and
the exact remaining acceptance run.

## Sources inspected

- <https://artiscan.ninjabay.org/>
- <https://artiscan.ninjabay.org/manifest.json>
- <https://artiscan.ninjabay.org/assets/index-CiH7InC-.js>
- <https://artiscan.ninjabay.org/assets/main-D3gZNFwd.js>
- <https://artiscan.ninjabay.org/sw.js>
