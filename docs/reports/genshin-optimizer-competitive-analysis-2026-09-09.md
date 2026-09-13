# Competitive analysis: Genshin Optimizer products

- Date: 2026-09-09
- Scope: product and architecture baseline for GrindLess v0.19

## Executive conclusion

Canonical open-source Genshin Optimizer is the main technical competitor. It is
substantially ahead of GrindLess in numerical build optimization. The smaller
`genshinoptimizer.com` product is useful as a simple UX reference, but it is not
an adequate benchmark for formula correctness.

GrindLess should not claim to outperform either product merely because it can
rank artifacts. Its defensible advantage is the closed loop they do not own:
capture account state, choose a goal, spend according to an explicit resin
policy, observe actual rewards, stop safely and explain every decision.

## Products compared

| Product | Observed role | Strongest capabilities | Boundary relevant to GrindLess |
| --- | --- | --- | --- |
| [Open-source Genshin Optimizer](https://frzyc.github.io/genshin-optimizer/) | Mature build and damage optimizer | Characters, weapons, artifacts, teams, loadouts, formulas, constraints, GOOD v3, Artifact Upgrader | External scanners and manual database import; no live farming loop or game control |
| [GenshinOptimizer.com](https://www.genshinoptimizer.com/#optimizer) | Lightweight local Top-10 tool | Fast GOOD import, simple filters, CV/ER/weak-slot presentation | Narrower model and no execution loop |
| GrindLess | Simulator-first farming agent | Integrated experimental video import, GOOD v1–v3 profile import, per-slot goals, two resin policies, safe stop, LLM audit, Linux/X11 control foundation | Narrow Mavuika solver; no universal formulas or live route yet |

## What open-source Genshin Optimizer already has

- Full character, weapon and artifact inventory with multiple local databases.
- Character levels, ascension, talents, constellations and weapon refinements.
- Team context, loadouts, buffs, reaction and enemy-defense parameters.
- Formula-level optimization targets with minimum build constraints.
- Artifact main-stat, level, set and exclusion filters, partial builds and
  protection of teammate artifacts.
- Exact roll and roll-value views, duplicate and upgrade detection, and an
  Artifact Upgrader for probabilistic upgrade questions.
- GOOD v3 documentation covering characters, artifacts, weapons and materials.
- An explicit scanner directory that includes Artiscan and Inventory Kamera.

## What GrindLess is missing

1. A universal formula engine and legal main-stat model for every character.
2. Team, rotation, reaction and enemy-context evaluation.
3. Top-K complete builds with global constraints and a captured canonical GO
   result for the now-frozen Mavuika GOOD v3 parity fixture.
4. Roll-value and upgraded-artifact analysis at the mature optimizer's depth.
5. Broad character presets, migration-safe game data and update cadence.
6. A packaged desktop release and a proven live dungeon end-to-end run.

## Where GrindLess can be better

| User task | Existing optimizers | GrindLess target |
| --- | --- | --- |
| Get account data | Run an external scanner, export GOOD, import manually | Select one video; local adapter runs Artiscan and validates GOOD automatically |
| Decide what to farm | Optimize current inventory | Compare artifact farming with guaranteed weapon or talent upgrades |
| Control resource spend | Show results or a resin counter | Ask economy versus full-budget policy before the run |
| React to a reward | User rescans and re-optimizes | Observe each confirmed reward in economy mode |
| Stop | User interprets optimizer output | Stop when every declared slot has its first qualifying improvement, budget ends, progress is unsafe or another goal is better |
| Act in the game | Not supported | Permission-gated external GameAdapter with emergency stop and no process injection |
| Explain | Build metrics | Deterministic trace plus optional LLM explanation and token/cost audit |

The upgrade overlap must be stated carefully. Genshin Optimizer's Artifact
Upgrader already helps assess possible artifact upgrades. GrindLess's distinct
default is not to simulate a single invented `+0 -> +20` outcome. It evaluates
observed substat content and, only after explicit permission, can enhance and
re-read the actual rolls.

## Evaluation contract

The first parity suite should use one frozen Mavuika C2 profile with Wolf's
Gravestone R1 and the declared Mavuika/Citlali/Xilonen/Bennett team. For the
same GOOD snapshot and build constraints, record:

- legal candidates per slot;
- best complete build and Top-K ordering;
- final set composition and ER constraint;
- ATK% versus EM sands result under the same rotation assumptions;
- expected deltas when one artifact is added, removed or equipped elsewhere.

Until those cases pass, the UI must label GrindLess as a narrow artifact-content
agent rather than a superior universal optimizer.

Implementation update: GrindLess 0.17 now imports the verified GOOD v1–v3
character, weapon and equipped-state subset and commits the frozen Mavuika input
plus its own deterministic golden result. The canonical GO result has not yet
been captured, so optimizer parity remains pending. See
`mavuika-go-parity-baseline-v1.md`.

## Primary sources

- Application: <https://frzyc.github.io/genshin-optimizer/>
- Scanner support: <https://frzyc.github.io/genshin-optimizer/#/scanner>
- Tools: <https://frzyc.github.io/genshin-optimizer/#/tools>
- Repository: <https://github.com/frzyc/genshin-optimizer>
- License: <https://github.com/frzyc/genshin-optimizer/blob/master/LICENSE>
- Lightweight product: <https://www.genshinoptimizer.com/#optimizer>
