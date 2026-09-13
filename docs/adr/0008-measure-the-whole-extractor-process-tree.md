# ADR 0008: Measure the whole extractor process tree

- Status: accepted
- Date: 2026-09-09

## Context

The first successful macOS Artiscan run established OCR accuracy and the
adapter-level network boundary, but it did not record wall time or peak memory.
Measuring only the Python process would materially understate consumption:
Playwright launches a driver and Chromium launches renderer, worker and utility
processes that perform video decoding, FFmpeg/Wasm and OCR work.

A shell-level one-off measurement would be easy to forget, hard to compare and
would not become part of the evidence trace. Repeated evals also cannot share a
single fixed output path without overwriting earlier results.

## Decision

Every browser video extraction produces a nested `performance` object in its
audit. The measurement contract is:

- use a monotonic clock around the entire session runner;
- sample every 100 ms;
- record peak RSS for the Python process;
- record peak summed RSS for Python and all recursive descendant processes;
- record interval, number of samples, completeness, warnings and a textual
  metric definition;
- require the monitor to verify that the root PID resolves to the current
  Python executable; otherwise stop instead of returning a misleading value.

`psutil` is added only to the optional `browser` dependencies. Simulator and
direct GOOD import remain free of process-monitoring dependencies. The macOS
launcher prints the two primary measurements and writes each run to a distinct
UTC-timestamped directory.

## Consequences

- New `run-report.json` files own their performance evidence instead of relying
  on a manually copied terminal value.
- The process-tree metric includes Chromium and is comparable across repeated
  runs on the same machine.
- Summed RSS may double-count shared pages and a 100 ms sampler can miss shorter
  spikes; reports describe these limits and must not call the value unique
  physical memory.
- Old reports without `performance` remain valid historical records but cannot
  contribute to runtime or memory percentiles.
- At least 30 preserved successful reports are still required before publishing
  P50/P95 claims.
