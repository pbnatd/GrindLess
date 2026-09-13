# ADR 0023: Generalize targets and accumulate Enka showcases

- Status: accepted
- Date: 2026-09-10

## Context

The first application slice hard-coded Mavuika, one target team and one domain
team. Artiscan returns the full artifact inventory but not a reliable account
roster. Enka returns detailed builds only for characters currently placed in a
public showcase. A missing character therefore cannot be interpreted as
unowned, and one showcase may not cover every target-team candidate and domain
runner the user wants evaluated.

Team selection and executable rotations also have different correctness needs.
An LLM can interpret preferences and explain trade-offs, but it must not be the
sole authority for numerical team ranking or low-level game actions.

## Decision

1. Add a versioned character catalog. Eight characters initially own complete
   artifact target profiles: Mavuika, Neuvillette, Arlecchino, Nahida,
   Xiangling, Noelle, Kaeya and Lisa. Additional catalog entries may be selected
   as teammates without yet claiming complete target support.
2. Record target-team and domain-team intent separately. A separate target team
   optimizes DPS; a domain team optimizes stability. When the same team serves
   both purposes, stability becomes the primary objective.
3. For automatic selection, require the user to provide an explicit candidate
   pool. The system may claim only “best among imported candidates”, never best
   across an unseen account roster.
4. Derive the expected showcase list from the selected target, manual teams and
   candidate pool. Compare this list with every Enka response and report exact
   missing characters instead of asking the user whether the showcase fit.
5. Allow several Enka showcase snapshots to merge into one local collection.
   The newest observation for a repeated character wins and keeps its capture
   timestamp. Artiscan/GOOD remains the sole full artifact-inventory authority;
   Enka artifacts are not merged into it.
6. Send a UID only after explicit consent, honor Enka's response TTL, and issue
   an opaque collection ID. The collection stores no full UID, is bound to a
   process-secret HMAC proof, stays in process memory for at most 30 minutes
   after its last merge, and is never written to SQLite.
7. Character artifact goals remain deterministic and versioned. A future
   `TeamOptimizer` and `RotationValidator` will own ranking and executable
   rotations; an LLM may translate preferences and narrate their evidence but
   cannot directly execute free-form rotation text.

## Consequences

- The onboarding flow works for eight distinct targets and can collect the
  exact teammate evidence needed across several showcase updates.
- Users must wait for Enka TTL before a changed showcase can be observed.
- Automatic team selection is explicitly pending until the deterministic
  optimizer exists; the UI can collect its complete input without pretending a
  recommendation has already been calculated.
- Expanding full target support requires a reviewed catalog profile and tests,
  not a new application branch.

## Rejected alternatives

- **Treat a missing Enka character as unowned.** Rejected because Enka exposes
  only the public showcase.
- **Merge Enka artifacts with Artiscan.** Rejected because the showcase is
  partial and would duplicate the inventory authority.
- **Let an LLM emit actions for the game adapter.** Rejected because cooldown,
  energy, focus and recovery states require a validated finite-state contract.
