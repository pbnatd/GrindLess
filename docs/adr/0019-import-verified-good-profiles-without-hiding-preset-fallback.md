# ADR 0019: Import verified GOOD profiles without hiding preset fallback

- Status: accepted
- Date: 2026-09-09

## Context

Artiscan commonly exports artifacts without characters or weapons, while the
canonical GOOD schema also supports complete character and weapon snapshots.
GrindLess previously accepted every positive GOOD version and always displayed
the fixed Mavuika C2 + Wolf's Gravestone R1 preset. This made an artifact-only
file look as if it had proved the profile and would silently ignore conflicting
account data.

The canonical open-source Genshin Optimizer repository at commit
`180a0a1015cb725c7570cd828eb086749960df98` accepts only GOOD versions 1, 2 and
3. Its GOOD 3 artifact extension adds `totalRolls`, `astralMark`,
`elixirCrafted`, `unactivatedSubstats` and `initialValue`.

## Decision

1. Accept root GOOD versions 1, 2 and 3 only and type the verified character,
   weapon and relevant GOOD 3 artifact fields.
2. Preserve active and unactivated substats separately. Both count as observed
   substat types in content-only ranking; inactive values do not enter numeric
   build totals.
3. Reject duplicate character profiles, duplicate equipped weapons, duplicate
   equipped artifact slots, unknown slots/stats and unsupported versions.
4. Preserve partial scanner exports. A location without a corresponding
   character record is a warning, not invented character data.
5. Return explicit `ProfileEvidence`: `good_inventory`, `mixed`, or
   `fixed_preset`. Reject imported Mavuika constellation, weapon or refinement
   that conflicts with the frozen parity profile.
6. Freeze `examples/mavuika.good-v3.json` and a deterministic GrindLess golden
   selection. Do not call it optimizer parity until the same fixture's result is
   captured from canonical Genshin Optimizer.

## Consequences

- The UI can distinguish facts from the uploaded file and fields confirmed by
  the user as a preset.
- Existing artifact-only Artiscan exports continue to work.
- Future schema versions fail visibly until reviewed.
- GOOD v3 inactive lines improve content analysis without pretending their
  future roll values are known.
- The fixture is reproducible but is only one half of a cross-tool parity test.

## Rejected alternatives

- **Require a full GOOD profile for every import.** Rejected because the proven
  video/Artiscan path legitimately exports artifacts only.
- **Silently prefer the preset over imported data.** Rejected because it hides a
  material evaluation mismatch.
- **Treat every future version like v1.** Rejected because a changed schema can
  produce plausible but incorrect account state.
