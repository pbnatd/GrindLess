# ADR 0024: Make the LLM the strategic agent

- Status: accepted
- Date: 2026-09-10
- Supersedes: ADR 0012 for decision ownership; its provider, quota, privacy and audit boundaries remain accepted
- Amends: ADR 0023 decision 7

## Context

The first provider integration restricted Qwen and GPT Luna to narration after
the deterministic core had already chosen every outcome. That made provider
behavior reproducible and safe, but it also reduced the product to an optimizer
with generated explanations. GrindLess is intended to be an agent: a model must
interpret the user's intent, decompose the goal, use tools, reconsider the plan
after observations and choose the next strategic action.

Giving a model raw control would create the opposite problem. Artifact fields,
resin accounting, legal actions, screen confidence and input safety are facts
or invariants. They must not change with sampling temperature or stale model
knowledge.

## Decision

The LLM is the strategic decision owner. It will:

1. choose and explain target-team and domain-team strategies from the explicit
   imported roster and user preferences; the user independently chooses
   `max_dps`, `comfort`, or `stable_rotation` for each team, and the model may
   not rewrite either objective;
2. produce structured artifact goals for the chosen character, weapon, team
   and role;
3. create and revise a structured domain rotation;
4. choose `continue`, `stop` or `change_goal` after each economy checkpoint.

The model reaches those decisions by calling typed tools. Tools remain the sole
owners of parsed GOOD/Enka facts, game-data retrieval, arithmetic, candidate
comparison, resin accounting, rotation validation, observation confidence and
allowlisted input execution. A proposed team, goal, rotation or action is not
executable until its schema and domain constraints pass. Unexpected or
ambiguous states fail visibly rather than being completed from model guesses.

The live control loop operates at a semantic level. The LLM chooses an
allowlisted macro-action from validated state; a deterministic controller
executes the timing-sensitive key sequence. Free-form model text never reaches
the keyboard or mouse adapter.

For a normal session, the planned model budget is:

- one call for account and team analysis;
- one call for artifact-goal construction;
- one call for rotation construction;
- in economy mode, up to one call per claimed reward, with all artifacts from
  that reward batched into the checkpoint;
- one final review;
- zero to two recovery calls only after a validated unexpected state.

This yields about four calls for `spend_all` and five to fourteen calls for a
200-resin `economy` session. The exact prompt, tool evidence, provider response,
usage and selected action remain auditable under the existing provider ledger.

## Consequences

- GrindLess becomes an agentic planner rather than a deterministic calculator
  with an LLM narrator.
- Numerical truth and safety remain reproducible even when model reasoning is
  nondeterministic.
- `TeamOptimizer` changes from the sole team decision owner into a ranking and
  validation tool used by the model. `RotationValidator` validates and compiles
  the model's structured plan.
- Version 0.23 delivers the first bounded loop: typed Enka/team evidence, one
  model-owned team-strategy decision and deterministic guard validation in
  shadow mode.
- Version 0.24 delivers the second loop: a compact GOOD/Enka projection, one
  model-owned artifact-goal decision, validation against curated sets and legal
  stats, a local inventory re-audit and use of the accepted goal by the teaching
  simulator. Exact off-piece optimization remains pending.
- Version 0.25 delivers the third bounded loop: the model creates a semantic
  rotation for the confirmed domain team, and `RotationValidator` compiles it
  into auditable primary/recovery states. Every burst has an unavailable policy,
  every failed confirmation leads to `safe_stop`, and the complete plan is
  revalidated before the simulator records it. Validation remains structural;
  timing, cooldown, energy and enemy-state knowledge are explicitly unverified,
  input authority remains absent and no plan reaches the game adapter.
- Version 0.26 makes team objectives explicit user-owned inputs. The target and
  domain objectives remain independent even when one composition serves both
  contexts; the model explains the compromise and the validator rejects a
  changed objective.
- Model-owned `continue`, `stop` and `change_goal` checkpoint decisions remain
  the next loop and require their own typed evidence and guard-compliance evals.

## Rejected alternatives

- **Narration-only LLM.** Rejected because the model cannot adapt goals or own
  the strategy and the product is not meaningfully agentic.
- **LLM-only calculations and control.** Rejected because unverifiable facts
  and free-form actions can consume resources or operate the wrong UI state.
- **One model call for every individual artifact.** Rejected because artifacts
  from one reward form a single observation and can be evaluated together.
