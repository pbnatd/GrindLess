# ADR 0029 — Rank researched team alternatives with a deterministic rubric

- Status: accepted
- Date: 2026-09-11
- Supersedes: ADR 0024 only for acceptance ownership of team strategy; its LLM strategy ownership and all other decisions remain accepted
- Amends: [ADR 0028](0028-require-web-research-for-strategic-game-knowledge.md)

## Context

Required web research fixed missing knowledge about current kits, reactions and
published rotations, but one researched model answer could still select a
plausible-looking weak or inconvenient composition. The previous validator
proved only boundaries: four unique confirmed characters, the target in the
target team, exact manual teams, allowed pools and preserved objectives. It did
not compare alternatives or explain why a composition was accepted over another.

A full damage simulator is not yet available and should not be imitated with a
made-up DPS number. The system nevertheless needs a stable, inspectable quality
gate before accepting model-owned strategy.

## Decision

The strategic model returns one to five structured candidates for both the
target and domain decisions. Automatic selection must include at least two
distinct alternatives whenever the declared pool permits more than one legal
composition. Manual and same-team decisions may provide one exact composition.

Each candidate contains researched 0–5 evidence for damage potential, reaction
coherence, rotation stability, energy feasibility, comfort and account
readiness and domain compatibility, plus an explicit `mechanics_verified` flag
and human-readable evidence. The evidence includes the target's allowed artifact
sets so the model researches the current enemies and restrictions of their
domains before rating the domain team.
These are bounded research claims, not authoritative combat measurements.

`TeamEvaluator` is the sole owner of versioned weights, thresholds and hard
quality gates. It:

1. rechecks uniqueness, Enka presence, allowed pools, target inclusion and exact
   manual/same-team constraints;
2. enforces explicit nearby character exclusions parsed from user preferences;
3. rejects unverified mechanics, incoherent reactions, infeasible energy,
   domain incompatibility and objective-specific minimum failures;
4. applies objective-specific weights and an acceptance threshold;
5. stores the full score breakdown, evidence and rejection reasons; and
6. selects the highest-scoring accepted candidate with stable input-order
   tie-breaking.

If either team has no accepted candidate, the first provider output is marked
`invalid_output`. The same selected model receives exactly one quality retry
with the evaluator's rejection reasons and the same reasoning/web-search
contract. A second failure stops visibly. Syntax-cutoff recovery remains a
separate transport repair and never bypasses evaluation.

The public result reports `decision_owner: llm_plus_team_evaluator` and
`exact_dps_claimed: false`. The LLM still owns strategic proposals and researched
game interpretation; the deterministic evaluator owns acceptance and ranking.

## Consequences

- Weak and conflicting candidates are no longer accepted merely because they
  satisfy the JSON schema and roster boundaries.
- The UI can explain the selected team and every rejected alternative with the
  same stored evidence that produced the decision.
- Explicit exclusions such as “не использовать Беннета” become enforceable
  local constraints. More semantic or scoped preferences remain model-owned and
  must still be explained in `preference_handling_ru`.
- The extra quality retry can increase a team-planning session from one call to
  two successful provider attempts; quota and token audit record both.
- The rubric ranks candidates but does not prove exact DPS. A future combat
  simulator may replace the research scores while preserving this evaluator
  boundary and result shape.

## Rejected alternatives

- **Trust the model's single favourite team.** Rejected because it repeats the
  failure that motivated this decision and leaves no comparison evidence.
- **Let the model calculate a precise DPS number.** Rejected because current
  account, enemy, animation and rotation telemetry are insufficient authority.
- **Put all live kits into a hand-maintained local database first.** Rejected as
  the immediate path because game knowledge changes faster than the project can
  curate complete versioned formulas; web research remains the current layer.
