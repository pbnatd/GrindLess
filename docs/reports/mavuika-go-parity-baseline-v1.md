# Mavuika parity baseline v1

- Date: 2026-09-09
- GrindLess version: 0.19.0
- Canonical baseline commit inspected:
  `180a0a1015cb725c7570cd828eb086749960df98`
- Status: GrindLess golden ready; canonical GO result capture pending

## Purpose

This fixture turns “compare with Genshin Optimizer” into a reproducible test,
without claiming a comparison that has not yet been run. The input is
`examples/mavuika.good-v3.json`; the machine-readable expected GrindLess result
is `tests/fixtures/mavuika-parity-expected.json`.

## Frozen account state

| Field | Value | Evidence |
| --- | --- | --- |
| Character | Mavuika level 90, ascension 6, C2 | GOOD v3 character |
| Talents | 6 / 10 / 10 | GOOD v3 character |
| Weapon | Wolf's Gravestone level 90, ascension 6, R1 | GOOD v3 equipped weapon |
| Target team | Mavuika / Citlali / Xilonen / Bennett | GrindLess parity preset |
| Artifacts on Mavuika | none | all fixture artifact locations are empty |
| Target set | Obsidian Codex, four pieces | GrindLess goal |
| Sands conflict | ATK% and EM equal at content stage | unresolved until a shared rotation target exists |

The seven artifact candidates cover all five slots, both sands main stats and
both circlet crit main stats. One sands uses GOOD 3 `unactivatedSubstats`, which
proves that known inactive content is retained without adding it to active
numeric totals.

## Current GrindLess golden

| Slot | Selected source index | Reason at content-only stage |
| --- | ---: | --- |
| Flower | 1 | legal main/set and four useful substat types |
| Plume | 2 | legal main/set and four useful substat types |
| Sands | 3 | ATK% and EM remain equal; stable source order breaks the content tie |
| Goblet | 5 | Pyro DMG has higher declared main-stat priority than ATK% |
| Circlet | 6 | CR and CD remain equal; stable source order breaks the content tie |

All five initial content goals close. This is not a damage-optimality claim:
numeric substat values, buffs, enemy state and rotation are deliberately absent
from the current content-only decision.

## Canonical GO capture protocol

1. Import the exact fixture into canonical open-source Genshin Optimizer.
2. Confirm Mavuika C2, Wolf's Gravestone R1 and empty artifact equipment.
3. Set the same target team and freeze one explicit optimization target and
   rotation assumption before comparing ATK% against EM sands.
4. Apply the same Obsidian Codex and legal main-stat filters.
5. Export the Top-K result or record its artifact source indices and settings.
6. Store the result beside the golden file and classify every difference as
   schema, legality, constraint, formula or tie-breaking.

Until step 5 is complete, the application correctly says “baseline prepared,”
not “parity passed.”

## Verified schema source

The inspected repository defines the GOOD root version as the union `1 | 2 | 3`
and documents character, weapon and GOOD 3 artifact fields in
`libs/gi/good/src/schemas/good-format.ts` and
`libs/gi/page-doc/src/index.tsx`. The fixture identifiers `Mavuika`,
`WolfsGravestone` and `ObsidianCodex` are present in the same source tree.
