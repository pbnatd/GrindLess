# ADR 0012: Separate LLM providers and local ledgers from the agent core

- Status: accepted
- Date: 2026-09-09

## Context

The project needs a one-computer demonstration now and an authenticated
multi-user deployment later. Optional GPT Luna and local Qwen explanations must
not make artifact choices nondeterministic, leak the raw inventory, hide API
usage, or force the agent core to know where a model or quota database runs.

Economy mode may reach a checkpoint after every reward and a final explanation;
spend-all reaches only the final explanation. A fixed two-call budget therefore
does not describe the actual workload.

## Decision

Keep scoring, slot acceptance and stopping entirely in `GrindLessAgent` and the
optimizer. Inject a `Narrator` backed by a replaceable `LLMProvider` only to
explain already structured evidence.

For the local demonstration:

- use the Responses API contract for OpenAI and OpenAI-compatible local Qwen;
- reserve each attempted call atomically in SQLite and enforce 40 successful
  calls per UTC day and 400 per UTC month by default;
- record exact transmitted text, provider-called state, response or error and
  returned token usage;
- fall back visibly to the deterministic template if a provider call fails;
- save completed session projections in SQLite without the raw GOOD inventory;
- load the OpenAI key from macOS Keychain or the process environment, never from
  the repository or SQLite.

Model IDs are configuration, not domain constants. `gpt-5.6-luna` is the demo
default requested by the project, but startup status and runtime failures must
remain visible when that exact ID is unavailable to an API account.

For a later multi-user deployment, preserve the provider and response contracts
while replacing local key access, quota ledger and session store with an
authenticated server gateway, per-user allowances and a shared hard cap.

## Consequences

- Offline tests and artifact decisions remain deterministic.
- The number of billed calls follows checkpoints actually reached: up to eleven
  for a 200-resin economy session, or one for spend-all.
- Users can verify exactly what left the computer; raw GOOD does not.
- A failed network request is truthfully marked as data sent if the provider was
  called, even when no response was received.
- Local history is intentionally one-user and is not represented as server
  access control.
- Scaling changes deployment adapters rather than optimization and stop logic.
