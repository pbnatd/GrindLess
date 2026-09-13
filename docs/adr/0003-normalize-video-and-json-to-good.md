# ADR 0003: Normalize video and JSON inventory inputs to GOOD

- Status: accepted
- Date: 2026-09-08
- Partially superseded by: [ADR 0005](0005-use-an-explicit-local-browser-artiscan-adapter.md)

## Context

Users should not need to make a separate screenshot for every artifact. Artiscan
can derive an inventory export from a continuous screen recording, while some
users will already have its JSON result. The terms JSON and GOOD were previously
presented as if they were separate input formats, although JSON is only the file
syntax and GOOD is the schema contained in that file.

The agent also must not depend on undocumented automation of the Artiscan web
interface. That would make inventory acquisition brittle and would hide a
third-party availability and privacy boundary inside the core decision loop.

## Decision

Expose two user-facing acquisition paths and normalize both before planning:

1. Preferred: raw inventory video is passed to a configured
   `VideoInventoryExtractor`, which returns a GOOD document.
2. Direct: the user uploads an Artiscan or other GOOD-compatible JSON document.

The validated GOOD inventory is the only internal input contract. File names
and `.json` versus `.good` extensions do not determine the schema; the root
`format` field does. The current MVP implements direct JSON import and the video
port. If no extractor is configured, video input fails loud and instructs the
user to export JSON from Artiscan. We do not automate the Artiscan website or
claim a stable API until one is documented and suitable for integration.

Artifact-only exports are valid inventories. A complete equipped build is
required only for operations that compare against the current character build;
candidate inspection must not reject an otherwise valid artifact-only file.

## Consequences

- The preferred UX can later accept one video without changing optimization or
  stop-policy code.
- Existing Artiscan JSON files work without conversion or renaming.
- External scanner availability is isolated behind one replaceable adapter.
- The system exposes when it lacks current equipment instead of inventing a
  baseline build.
- Video extraction accuracy and privacy need their own evals before the port is
  enabled in a live product.
