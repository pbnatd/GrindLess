# ADR 0028 — Require web research for strategic game knowledge

- Status: accepted
- Date: 2026-09-11
- Amends: [ADR 0024](0024-make-the-llm-the-strategic-agent.md)
- Amends: [ADR 0026](0026-version-curated-target-profiles-as-local-evidence.md)

## Context

The local target profiles are reliable for legality, set choices and bounded
artifact goals, but they cannot economically mirror every live character kit,
reaction rule, rotation and guide revision in Genshin Impact. Treating missing
local prose as missing game knowledge produced weak teams, vague rotations and
statements that published mechanics could not be confirmed. The UI also sent
free-form user preferences without requiring the model to account for them.

The target and domain teams are separate decisions. Requiring the target
character in the automatically selected domain team unnecessarily weakened the
domain optimizer.

## Decision

Strategic team, artifact-goal and rotation calls use an OpenAI Responses API
model selected by the user: Luna, Terra or Sol. The user also selects Low,
Medium or High reasoning. Astra and reasoning levels above High are not exposed.

Each strategic request requires the provider web-search tool. A response is
rejected if the audit does not show a successful web-search call. Provider-owned
source URLs are requested, extracted from tool results and citation annotations,
and returned to the UI. A syntactically truncated retry preserves the same model
reasoning level and web-search requirement.

The local knowledge base remains the authority for roster identity, artifact
legality, curated set options and deterministic validation. Web research is the
current knowledge layer for kits, reactions, team guides, energy mechanics and
published rotations. It does not grant input authority or turn web claims into
live game telemetry.

An optional user comment is a binding strategic instruction unless it conflicts
with a typed hard boundary. Every accepted structured response must include a
non-trivial `preference_handling_ru` explanation of how the comment was applied
or why it could not be.

Automatic domain selection is independent. It may choose any four confirmed
characters from the declared candidate pool, including or excluding the target
character. Manual and `same` modes retain their existing exact constraints.

## Consequences

- Current game knowledge no longer depends on expanding the local database for
  every new kit and reaction before useful planning is possible.
- Strategic planning now requires network access and a configured OpenAI key;
  offline and local-Qwen modes remain available for deterministic simulation or
  narration, not these live-research decisions.
- The audit and UI disclose that the model receives the bounded evidence,
  optional comment and web-search queries, and show the returned sources.
- Search failure or an ignored comment fails the strategic endpoint visibly
  instead of yielding a plausible but under-informed plan.
- Team quality still requires evaluation against curated fixtures; web research
  improves the knowledge input but is not a numeric damage simulator.
- All accepted rotations remain `structural_only`, `shadow_only` and
  `input_authority: none`.

