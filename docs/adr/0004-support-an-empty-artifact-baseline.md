# ADR 0004: Support an empty artifact baseline

- Status: accepted
- Date: 2026-09-08

## Context

The Mavuika demo character has no equipped artifacts. The Artiscan export
contains 108 unequipped level-zero artifacts and no `location` fields. Requiring
a complete equipped build would reject valid inventory data, while inventing a
baseline would make every later comparison and stop decision ungrounded.

The product also needs to distinguish “I can equip something in every slot”
from “every slot meets the agreed farming goal.” These states are not the same.

## Decision

Make baseline mode explicit. Existing scenarios use `equipped`; a character
with no artifacts uses `empty`.

For `empty`, run a deterministic initial-build audit before farming. For each
slot it selects the best available provisional candidate by allowed set, main
stat priority, desired substat types, number of useful types and number of
observed starting substats. Numeric substat values and hypothetical future rolls
do not participate. Source order is used only to make otherwise exact ties
stable.

The audit reports two independent facts:

- `starter_build_available`: every slot has some allowed provisional item;
- `pending_slots`: slots with no candidate meeting the preferred main-stat and
  minimum useful-substat contract.

The Mavuika preset records C2, Wolf's Gravestone R1, target team
Mavuika/Citlali/Xilonen/Bennett, and farming team
Nefer/Lauma/Columbina/Sucrose. ATK% and Elemental Mastery sands receive equal
main-stat priority at the +0 content stage. Their final ordering is deferred to
observed enhancement results and the rotation calculator.

## Consequences

- Artifact-only exports become useful without fake equipment data.
- A weak temporary item may fill a starter build but cannot stop farming a
  preferred slot.
- Economy mode needs a separate transition from initial audit to farming only
  the reported pending slots.
- The current implementation audits and reports that transition; executing the
  reduced farm goal is the next milestone.
- The preset is reproducible and can be replaced without character-specific
  branching in the importer.
