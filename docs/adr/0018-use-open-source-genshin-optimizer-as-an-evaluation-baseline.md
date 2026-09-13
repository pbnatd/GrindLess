# ADR 0018: Use open-source Genshin Optimizer as an evaluation baseline

- Status: accepted
- Date: 2026-09-09

## Context

There are two products with similar names. `genshinoptimizer.com` is a small
local-first Top-10 interface. The canonical open-source Genshin Optimizer at
`frzyc.github.io/genshin-optimizer` is a mature MIT-licensed project with full
character, weapon, artifact, team, loadout and damage-formula modeling.

GrindLess currently has a narrow Mavuika profile and an exact solver only for
small teaching inventories. Claiming optimizer parity would be false and
reimplementing the mature calculation engine before the project defense would
consume the work needed for the actual agent loop.

## Decision

1. Treat canonical open-source Genshin Optimizer as the primary numerical and
   data-model evaluation baseline. Treat `genshinoptimizer.com` only as a
   lightweight UX comparison.
2. Keep build selection behind the existing `BuildOptimizer` port. The agent,
   resin policy, game adapter and LLM narrator must not own artifact formulas.
3. For the MVP, validate a bounded Mavuika fixture against documented optimizer
   inputs and expected outcomes: team, weapon, constellation, legal main stats,
   set constraints and Top-K ordering.
4. Do not embed or call Genshin Optimizer in the runtime yet. A later TypeScript
   or Node adapter may reuse its MIT-licensed calculation code only after a
   separate audit of package boundaries, notices, game data and visual assets.
5. Preserve GrindLess's product differentiation outside the solver: integrated
   video import, explicit resin policy, observation after rewards, permission-
   gated enhancement, safe stop, game control and an auditable decision trace.

## Consequences

- The project has an honest external benchmark instead of claiming superiority
  from a narrower scoring heuristic.
- The current Python optimizer remains replaceable without changing the agent
  or simulator contracts.
- GOOD v3 characters, weapons and equipped state become a prerequisite for
  meaningful parity tests rather than a marketing claim.
- GrindLess can be better as a closed-loop farming agent before it is equal as a
  universal optimizer, and the UI must state that distinction explicitly.
- Reuse of MIT code is possible later, but license compatibility for adjacent
  datasets and assets is not assumed from the repository license alone.

## Rejected alternatives

- **Clone the full optimizer before the defense.** Rejected because it expands
  the MVP away from the agent loop and still needs extensive parity validation.
- **Let the LLM choose the best build.** Rejected because build arithmetic must
  be deterministic, testable and independent of narrator availability.
- **Use only `genshinoptimizer.com` as the competitor.** Rejected because it
  omits the much stronger canonical open-source baseline.
