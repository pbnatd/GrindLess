# ADR 0007: Compare GOOD exports by domain content

- Status: accepted
- Date: 2026-09-09

## Context

The first real macOS video run produced a valid 108-artifact GOOD document. A
byte-for-byte JSON comparison with the older reference would incorrectly report
all artifacts as different because the new export explicitly writes
`"location": ""` while the reference relies on GOOD's missing-field default.
Artifact and substat array order are also serialization choices rather than
gameplay facts.

At the same time, an eval must not hide a changed main stat, substat value,
equipped character or lock state. A documented reproducible equivalence rule is
needed before reporting OCR accuracy.

## Decision

Add `grindless-good-compare` as the reference-eval command. Both inputs must pass
the production GOOD importer. Each artifact's core signature contains:

- set and slot;
- rarity and level;
- main stat;
- the complete multiset of non-empty substat keys and normalized values;
- equipped location, with a missing field normalized to empty;
- lock state, with a missing field normalized to false.

The command compares the artifact signatures as multisets, so artifact order
and substat order do not affect exact accuracy. It separately emits positional
field metrics for recordings whose scan sequence is stable, reports raw
representation differences, and exits with a nonzero status when the core
inventories are not equivalent. Source and schema version are reported but do
not replace artifact comparison.

## Consequences

- The macOS fixture can be reported as 108/108 exact without conflating an
  explicit empty default with an OCR error.
- Changed gameplay content cannot be excused as formatting.
- Future video fixtures can use the same command in local evals and CI without
  committing private user inventories to the repository.
- Field accuracy for reordered, non-identical inventories needs a future
  alignment algorithm; the order-independent exact multiset score remains the
  acceptance gate.
