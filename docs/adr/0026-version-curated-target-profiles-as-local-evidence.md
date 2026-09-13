# ADR 0026: Version curated target profiles as local evidence

- Status: accepted
- Date: 2026-09-10
- Extends: ADR 0023 and ADR 0024

## Context

The first universal catalog exposed 116 team candidates but only eight artifact
targets. Their roles, sets and stat priorities were embedded in Python. That
made coverage difficult to audit or update and let the artifact LLM choose any
main stat that was mechanically legal for a slot and element, even when it was
outside the selected character's curated build profile.

The requested coverage is every currently playable limited five-star in the
bundled Genshin 7.0 roster. Standard-banner characters, Traveler and Aloy are
not limited event five-stars. Artifact advice also changes with teams,
rotations and newly released sets; a numeric benchmark is therefore not a
universal pass/fail threshold.

## Decision

1. `data/target_profiles.json` is the versioned source of truth for target
   support. Version 1 contains 56 currently playable limited five-stars plus
   the four previously supported starter targets.
2. Every profile records a role, primary and secondary four-piece set, ordered
   Sands/Goblet/Circlet choices, ordered substats, source URL, observed date,
   guide version when stated, contextual caveats and optional benchmarks.
3. KQM character guides are the primary curated build source. The roster and
   identity mapping remain sourced separately from Enka. Updating either
   dataset does not silently update the other.
4. Benchmarks are advisory evidence only. Each value carries its condition and
   `enforced: false`; ER remains unresolved until a concrete rotation is
   validated.
5. `CharacterDefinition` is enriched from the profile database at startup.
   Startup fails on duplicate, unknown or structurally incomplete profiles and
   on coverage other than 56 limited five-stars plus four starters.
6. `ArtifactGoalValidator` accepts main stats only from the selected
   character's local profile. Slot legality by itself is insufficient.
7. The existing optimizer still expresses one four-piece set at a time.
   Profiles whose best generic build can be 2pc+2pc must disclose that
   limitation instead of pretending exact mixed-set optimization exists.

## Consequences

- The target picker grows from 8 to 60 entries and therefore includes search.
- LLM artifact planning receives traceable local role, set, stat, benchmark and
  caveat evidence for every supported target.
- A model cannot introduce a formally legal but uncurated main stat.
- New banners require an explicit roster/profile review and version update.
- Conditional team variants and exact 2pc+2pc/off-piece optimization remain a
  later deterministic optimizer extension.

## Rejected alternatives

- **Let the LLM research every target live.** Rejected as the default because
  results would be slower, harder to reproduce and vulnerable to stale or
  low-quality pages.
- **Store only one set name and generic elemental stats.** Rejected because it
  erases team conditions and already allowed invalid strategic choices.
- **Turn guide benchmarks into hard requirements.** Rejected because most ER,
  HP, ATK and EM targets depend on weapon, teammates and rotation.
