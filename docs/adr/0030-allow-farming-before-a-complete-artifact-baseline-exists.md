# ADR 0030: Allow farming before a complete artifact baseline exists

- Status: accepted
- Date: 2026-09-11
- Supersedes: ADR 0011 and ADR 0027 only where they require a complete five-slot set composition before simulation
- Amends: ADR 0004

## Context

The initial-build audit intentionally considers target set, main-stat and
substat constraints. A legitimate new-build scenario can therefore contain many
imported artifacts but no eligible item for one or more slots, or five usable
temporary items that do not yet form the required 4pc or 2pc+2pc composition.

The application previously rejected both states before farming with
`cannot start a farm simulation without a valid five-slot baseline`. That made
the simulator unusable for the exact case where a player needs to acquire a
character's first suitable set. Filling missing slots with invented artifacts
would make later comparisons ungrounded.

## Decision

Treat the frozen simulation baseline as a partial `Build`.

- Freeze every artifact ID selected by the inventory audit; do not synthesize
  items for absent slots.
- Expose absent baseline and best-candidate IDs as `null` in per-slot progress.
- Compare an observed candidate with content score zero when the slot has no
  valid baseline.
- A first candidate closes an absent or invalid baseline slot only when it
  satisfies the declared set/main-stat eligibility and minimum useful-substat
  contract. Numeric rolls and hypothetical enhancement remain excluded.
- Continue to choose a complete required set signature when one is reachable.
  While it is not reachable, choose the observed state with the greatest
  progress toward that signature and keep unresolved selected slots open.
- Record frozen IDs and the list of empty slots in `session_started` evidence.
- Do not disable the UI path to rotation or simulation merely because the audit
  reports `starter_build_available=false`.

The user's explicit target-slot selection remains the stop boundary. Farming a
single selected slot can therefore finish after its first qualifying piece even
if the account still lacks a complete set in unselected slots; the UI does not
claim that the whole build is complete.

## Consequences

- A fresh character with no target-set pieces can enter the farming loop.
- Partial inventories and impossible initial set compositions no longer fail
  before the first synthetic reward.
- Results distinguish `null` baseline/candidate IDs from real artifact IDs and
  explain first acquisitions separately from improvements.
- Full valid baselines keep the previous frozen-comparison behavior.
- Consumers of `SlotProgress` must accept nullable artifact IDs, and consumers
  of `baseline_artifact_ids` must accept a partial slot mapping.
