# ADR 0001: Simulator-first environment boundary

- Status: accepted
- Date: 2026-09-08

## Context

GrindLess must demonstrate an autonomous observe-decide-act loop now and may
later operate one constrained Genshin Impact domain. Direct client automation
is risky, difficult to reproduce, and couples planning to unstable screen and
input details.

## Decision

Build the first working environment as `ArtifactDomainSimulator`. The agent can
interact with an environment only through `FarmAdapter`. A later experimental
`GameAdapter` must implement the same reward and enhancement contract, while
all artifact evaluation, resin policy, stop thresholds, and decision traces
remain in environment-independent domain code.

LLM providers are also replaceable. They may translate intent and explain a
calculated result but do not own arithmetic, inventory truth, safety checks, or
stop decisions.

## Consequences

- The agent loop and stop-policy can be tested without an account or game client.
- Simulator and live observations can share the same eval cases.
- The real adapter can fail closed without changing planning logic.
- Initial drop probabilities are approximations and must be calibrated before
  quantitative claims about expected Resin value.
- Real-client input is deliberately outside the first implementation.
