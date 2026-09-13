# ADR 0027: Model artifact set compositions and the flex piece explicitly

- Status: accepted
- Date: 2026-09-10
- Supersedes: ADR 0026 decision 7 and its deferred optimizer consequence

## Context

Artifact goals previously stored one `required_set` and a piece count. Each
slot also rejected artifacts outside that set. This could represent a 4pc
bonus only by treating every slot as an on-set slot: a better fifth artifact
from another set was invisible, 2pc+2pc was not expressible, and independent
slot choices could not move the flex piece when two coordinated replacements
were needed.

The LLM must choose strategy from curated options, but set legality and the
actual five-item selection must remain deterministic and reproducible from the
local GOOD inventory.

## Decision

1. `BuildConstraints.set_requirements` is the only authoritative set-bonus
   contract. It accepts no set requirement, one 4pc requirement, or two
   distinct 2pc requirements. The legacy single-set fields are removed.
2. The four required pieces are a global build constraint. Slot goals retain
   main-stat and substat criteria but do not restrict a set, leaving exactly
   one flexible fifth artifact for either supported composition.
3. The initial inventory audit uses dynamic programming over all five slots
   and capped required-set counts. It selects one coherent content-optimal
   build, reports selected set counts, whether the composition is met, and the
   exact flex artifact identifier.
4. Reward checkpoints optimize all targeted replacements together. This lets
   the flex piece move between slots while the required 4pc or 2pc+2pc bonus
   remains valid.
5. Target-profile schema version 2 may declare additional versioned set
   options. The two existing fields generate stable primary and secondary 4pc
   options; additional entries may declare curated 2pc+2pc compositions.
6. The LLM selects a stable option identifier, never arbitrary set names or
   counts. `ArtifactGoalValidator` resolves that identifier to requirements
   from the target profile and rejects any other composition.
7. Candidate observations remain bounded to six per slot, but may represent
   any five-star set. The complete GOOD inventory stays local and is used by
   the deterministic flex-piece optimizer.
8. Content-only scoring remains unchanged: observed main stat, substat types
   and visible line count are used; hypothetical future rolls are not.

## Consequences

- Every 4pc build can use its best exact off-piece instead of requiring five
  pieces from the selected set.
- Curated 2pc+2pc options are first-class and auditable. Nilou's versioned
  profile now includes 2pc Tenacity of the Millelith plus 2pc Vourukasha's
  Glow for the generic HP variant.
- A five-slot inventory without the required composition is reported as
  incomplete and cannot start the simulator.
- The API, rotation summary and UI now expose `set_requirements`, the selected
  option and the exact flex item. This is an intentional schema change.
- The dynamic program scales with slots and small capped set-count states, not
  with the Cartesian product of the whole inventory.
- Choosing the correct real farming domain for components that come from
  different domains remains a future planning problem; the teaching simulator
  only models the selected pair of set names.

## Rejected alternatives

- **Keep a set allowlist on every slot.** Rejected because it cannot represent
  a true off-piece and makes coordinated flex-slot movement impossible.
- **Ask the LLM to name two arbitrary sets.** Rejected because invented or
  stale set combinations would bypass the versioned local profile.
- **Pick the best artifact independently in each slot.** Rejected because five
  locally best choices may violate the global 4pc or 2pc+2pc constraint.
