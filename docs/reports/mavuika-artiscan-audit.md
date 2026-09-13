# Mavuika Artiscan inventory audit

- Date: 2026-09-08
- Input: user-provided `artifacts.json`
- Input contract: GOOD v1, source Artiscan
- Character context: Mavuika C2, Wolf's Gravestone R1
- Target team: Mavuika, Citlali, Xilonen, Bennett
- Farming team: Nefer, Lauma, Columbina, Sucrose
- Evaluation mode: level-zero content only

## Evidence

The strict importer accepted 108 five-star level-zero Obsidian Codex artifacts.
The export contains no characters, weapons or equipment locations. The audit
therefore used `baseline_mode=empty`; it did not infer a current build.

## Result

| Slot | Provisional candidate in source order | Observed useful substat types | Closes the initial goal? |
|---|---:|---|---|
| Flower | 1 | CRIT Rate, Elemental Mastery, ATK% | yes |
| Plume | 30 | CRIT DMG, Elemental Mastery, ATK% | yes |
| Sands | 57, ATK% main | CRIT DMG | no |
| Goblet | 64, temporary ATK% main | none | no |
| Circlet | 88, CRIT Rate main | ATK% | no |

A provisional five-slot build is possible, but the farming contract remains
open for sands, goblet and circlet. No Pyro DMG goblet is present. The one
Elemental Mastery sands has ATK% as its only useful percentage substat and no
CRIT type, so it also does not close the sands goal.

## Interpretation boundary

ATK% and Elemental Mastery sands are both allowed and have equal priority while
the artifacts remain at +0. The audit does not simulate enhancement and does
not use the numeric values of substats. A final ATK-versus-EM verdict requires
observed enhanced artifacts and a team rotation calculation.
