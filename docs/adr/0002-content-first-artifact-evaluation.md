# ADR 0002: Content-first artifact evaluation

- Status: accepted
- Date: 2026-09-08

## Context

A `+0` artifact has unknown future rolls. Simulating it to `+20` and treating
that sample as evidence can waste real enhancement materials or reject a good
candidate because of invented randomness. Enhancement itself is also a
resource-spending action that needs separate user authority.

## Decision

The default evaluator compares only observed content: allowed set, suitable
main-stat type, and the presence of desired substat types weighted by declared
build priorities. It ignores the numeric values of those substats and makes no
claim about future rolls. A match is called a promising candidate, not a proven
final upgrade.

Enhancement is disabled by default. A session may enable it only through an
explicit authorization containing a positive maximum number of artifacts and a
target level. The agent may spend that budget only on content-promising items;
after enhancement it compares the actual observed rolled values.

## Consequences

- Default runs cannot consume artifact EXP, Mora, or fodder.
- A user can enhance candidates manually and import the inventory again.
- Economy mode may stop on potential rather than guaranteed final power, so the
  explanation must preserve that distinction.
- Numeric build comparison remains available for observed enhanced artifacts,
  but hypothetical roll simulation is not stop evidence.
- Future real adapters must expose enhancement behind the same explicit budget.
