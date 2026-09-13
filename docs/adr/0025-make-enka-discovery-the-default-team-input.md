# ADR 0025: Make Enka discovery the default team input

- Status: accepted
- Date: 2026-09-10
- Supersedes: ADR 0023 decision 4 for the default onboarding path

## Context

ADR 0023 derived an exact Enka showcase checklist from teams or a candidate
pool selected in advance. That keeps evidence bounded, but it makes the user
search a catalog of more than one hundred characters before Enka can confirm
them. The common intent is simpler: the user already knows which characters
they want considered and can place them in the in-game showcase.

Enka exposes only the current public showcase. Absence is not account
ownership evidence, and one showcase may not fit everyone needed for two team
contexts. The application therefore cannot infer that discovery is complete.

## Decision

1. The default onboarding path is `discovery`: the user first places desired
   characters in Character Showcase, explicitly consents to the UID lookup and
   imports every catalog-known profile visible in that snapshot.
2. Several discovery snapshots may merge into the same 30-minute in-memory
   collection under the existing UID HMAC and TTL rules. The latest repeated
   profile wins. No full UID or collection is persisted.
3. After discovery, the user either selects exact teams from only the observed
   characters or exposes all observed non-target characters as the explicit
   candidate pool for LLM selection.
4. Discovery has no machine-inferred completion condition. The collection
   remains incomplete until the user explicitly says that all needed showcase
   snapshots have been added and submits the final `TeamIntent`.
5. Finalization validates the final plan against observed profiles. A missing
   target, manual member or required candidate fails visibly and prevents the
   strategic LLM call.
6. The earlier `planned` path remains supported: users may search the complete
   versioned roster first, derive an exact showcase checklist and merge
   snapshots until the checklist is satisfied.
7. Collection mode is immutable after the first snapshot. Switching between
   discovery and planned semantics requires a new collection so that
   completion evidence cannot silently change meaning.

## Consequences

- The main flow no longer requires searching the full roster before Enka.
- The showcase itself becomes the source of the explicit candidate pool, not
  evidence of the user's entire account roster.
- Both onboarding methods produce the same `TeamIntent`, `TeamPlan` and
  strategic validation contract after finalization.
- Users still wait for Enka TTL before a changed showcase can be observed.

## Rejected alternatives

- **Treat the first showcase as complete.** Rejected because a public showcase
  is partial and cannot reveal whether more desired characters exist.
- **Treat observed characters as the full owned roster.** Rejected because
  Enka does not expose account ownership outside the showcase.
- **Remove manual roster selection.** Rejected because some users already know
  exact teams or want an auditable predeclared checklist.
