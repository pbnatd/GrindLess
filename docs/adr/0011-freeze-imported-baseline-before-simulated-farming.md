# ADR 0011: Freeze the imported baseline before simulated farming

- Status: accepted
- Date: 2026-09-09

## Context

The first interface slice can select a provisional five-slot Mavuika build from
an artifact-only GOOD export. The next slice must demonstrate the closed-loop
agent: declare target slots, observe synthetic domain rewards, compare them with
the user's inventory and decide whether to repeat or stop.

Comparing every reward with an empty baseline would make almost any valid item
look like an upgrade. Re-running the initial-build optimizer after each reward
would also move the baseline and change the meaning of "first item better than
what I already had". Simulating unknown `+0 -> +20` rolls would fabricate the
evidence the user explicitly chose not to spend materials to observe.

## Decision

Before a simulation starts, the application service imports GOOD, runs the
empty-baseline audit and freezes its five selected artifact IDs as the session
baseline. The user selects one or more target slots, a policy, a resin budget in
20-resin increments and a deterministic seed.

The application then switches the session to an equipped-baseline comparison
and calls the existing `GrindLessAgent` through `ArtifactDomainSimulator`, the
same `FarmAdapter` boundary reserved for a future game adapter. The simulator
produces synthetic domain rewards only. Artifact enhancement remains disabled,
so all decisions use observed set, main-stat and substat types; numeric rolls and
hypothetical future upgrades do not participate.

The API returns both the domain result and a UI projection grouped by reward
claim. In `economy`, every confirmed reward is a checkpoint and the agent stops
when every selected slot has an accepted improvement. In `spend_all`, rewards
are staged and analyzed once after the selected budget is spent.

Simulator probabilities are explicitly labeled as teaching approximations. A
configured expected-gain comparison against weapons or talents remains disabled
until drop probabilities and guaranteed gains are calibrated.

## Consequences

- A simulation is grounded in the user's imported inventory instead of an
  invented character state.
- Repeating a seed reproduces the same evidence and stop decision.
- A missing five-slot provisional build fails before any synthetic reward is
  generated.
- The UI can explain every reward and the final stop without owning scoring
  rules.
- Real game integration later replaces only `FarmAdapter`; it does not replace
  the agent, optimizer, request contract or stop-policy semantics.
- Enhancement authorization will require a separate implementation that
  observes actual rolls; this simulator does not stand in for it.
