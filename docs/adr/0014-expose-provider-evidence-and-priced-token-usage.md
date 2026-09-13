# ADR 0014: Expose provider evidence and priced token usage

- Status: accepted
- Date: 2026-09-09

## Context

The local quota ledger proved that model calls were completed, but the UI only
showed per-call input and output token counts. A separate provider dashboard may
show zero because a different project, organization, filter or reporting window
is selected. Without the actual model and response identifier, the two records
are difficult to reconcile. A cost calculated from an assumed tariff would be
equally misleading.

## Decision

Extend the narration audit projection with the provider `response_id`, cached
input tokens, per-call estimated cost, aggregate input/output/total tokens,
aggregate estimated cost and a pricing-source note.

For the exact default model `gpt-5.6-luna`, use OpenAI's public prices observed
on 2026-09-09: $0.20 per million uncached input tokens, $0.02 per million cached
input tokens and $1.20 per million output tokens. Any other model has no price
unless all relevant rates are explicitly configured. Missing or partial custom
pricing produces no plausible cost; partial configuration fails loudly.

The estimate is explanatory evidence, not billing authority. Provider billing
remains authoritative, and the audit preserves the returned token usage rather
than estimating tokens from characters.

## Consequences

- A successful call can be matched to provider evidence by response identifier.
- The UI shows session totals instead of requiring manual addition.
- Model changes cannot silently reuse Luna pricing.
- Cached tokens receive their own rate when the provider reports them.
- Historical sessions created before this schema extension may need a display
  compatibility migration if they are retained across prototype releases.
