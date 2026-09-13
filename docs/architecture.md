# Architecture

## Core rule

The LLM owns strategic choices; typed tools own imported facts, arithmetic,
validation, safety and execution. The environment adapter owns how a reward is
obtained and, only when authorized, how an artifact is enhanced. The optimizer
owns content and numeric comparisons. Free-form model output never reaches the
game-control adapter.

Version 0.34 implements the first three ADR 0024 slices. Account/team evidence is built
by a typed tool, an LLM researches and proposes target/domain alternatives, and
`TeamEvaluator` ranks those proposals before `TeamStrategyValidator` enforces
manual compositions, explicit candidate pools, Enka presence and
four-unique-character constraints. The accepted plan remains
`shadow_only`. After GOOD import, `ArtifactEvidenceTool` sends only a bounded
projection of the target, confirmed teams, equipped weapon key and at most six
artifact observations per slot. A second model call owns the set, main-stat,
substat and slot-priority choices. `ArtifactGoalValidator` rejects unknown sets,
illegal stats, missing slots and duplicates, deterministically builds a
`FarmGoal`, and re-audits the local inventory. A third call builds the semantic
domain rotation, which is compiled into safe-stop states without input authority.
Strategic `continue`/`stop`/`change_goal` ownership is still pending.

The inventory-input layer separately owns acquisition and normalization. The
agent never reasons over raw OCR text or video frames: both video and an
already exported JSON must become one validated GOOD-domain inventory first.

## Platform boundary

Platform support is capability-specific rather than one yes/no flag for the
whole product. `platform_support` is the runtime owner of this matrix:

| Host or source device | Core and GOOD | Local video extraction | Local LLM | Direct game execution |
|---|---|---|---|---|
| macOS desktop | available | experimental | compatible endpoint; runtime package pending | unavailable |
| Windows desktop | available | experimental | compatible endpoint; runtime package pending | planned shadow adapter; not implemented |
| Linux desktop | available | experimental | compatible endpoint; runtime package pending | experimental X11 probe/capture/guarded input; route pending |
| PlayStation / Xbox | desktop companion only | process an exported recording on a desktop | runs on companion | unavailable |
| iOS / Android | outside MVP; desktop companion is possible | process an exported recording on a desktop | runs on companion | unavailable |

The portable core never imports OS input APIs. Each `GameAdapter` must be
a separately enabled plug-in with its own permissions, screen-state contract,
safety evidence and evaluation. Detecting Windows is not equivalent to having a
working executor. An unknown platform fails capability discovery loudly.

### Linux/X11 game-control boundary

`linux_game_adapter` owns the first platform implementation. Its probe records
the host, X11 session, display, required executables, unique window identity,
window geometry and foreground-focus observation. The application exposes this
evidence without enabling input.

`LinuxX11GameControl` owns only capture and allowlisted OS input. Input is
disarmed unless `GRINDLESS_ENABLE_GAME_INPUT=1` was present when the environment
was probed. Every action re-checks focus and 1920x1080 geometry and then checks
the stop file and top-left pointer fail-safe. It does not implement
`FarmAdapter`: route execution, reward confirmation and artifact observation
remain pending.

Version 0.35.0 adds the first separate observation authority. A
`ScreenReferenceStore` holds operator-confirmed 1920x1080 reference captures and
a checksummed versioned manifest. `CalibratedScreenClassifier` returns a known
state only above the `0.95` similarity threshold and with a `0.02` margin over a
different state. `ShadowGameObserver` checks the fixed route transition graph,
records the evidence for every sample and stops on unknown or ambiguous frames,
illegal transitions, the operator stop file, 12 transitions or five minutes.
It never calls the input methods and always reports `input_authority: none`.
The sampled PNG files and the final JSON trace stay under the user's local
`~/.grindless/game-shadow-runs` directory so every classifier result can be
reconstructed and retuned; they are not transmitted by the adapter.
This calibrated observer is not yet a `FarmAdapter`; it provides the local
fixtures required to build and evaluate one fixed-domain route without guessing.

The reference game runs through An Anime Game Launcher/Wine, but GrindLess is a
separate native process outside the launcher's Flatpak. There is no injection,
process-memory read, game-file modification, credential handling, anti-cheat
bypass or traffic interception. This boundary is still automation and is not
represented as ban-safe.

```text
goal -> agent -> FarmAdapter -> reward observation
          |                         |
          +---- optimizer <---------+
          |
          +---- stop-policy -> repeat / stop / change_goal / safe_stop
          |
          +---- narrator -> explanation
```

No adapter may redefine whether an artifact satisfies a goal. It returns
observations; the domain layer decides.

## Inventory input boundary

Two user-facing paths converge before any planning:

1. Preferred product flow: `video -> Artiscan-compatible extractor -> GOOD JSON`.
2. Direct flow: `Artiscan/GOOD JSON -> schema validation`.

JSON describes the serialization syntax; GOOD describes the schema. Therefore
an Artiscan file named `artifacts.json` whose root contains `"format": "GOOD"`
is already a GOOD input and is not converted again.

`import_good` accepts only GOOD versions 1, 2 and 3. It preserves character
level/ascension/constellation/talents, weapon level/ascension/refinement,
equipped locations and GOOD v3 artifact metadata. Active and unactivated
substats remain distinct: both are known content for the default type-only
ranking, while only active observed values can enter numeric build totals.
Duplicate character profiles, two weapons on one character, two artifacts in
one equipped slot, unknown slots/stats and future GOOD versions fail loudly.
An equipment location whose character record is absent is retained with a
warning because artifact-only scanner exports are valid partial snapshots.

`VideoInventoryExtractor` owns video-to-GOOD conversion. No stable Artiscan
server API is assumed: without an explicitly selected extractor, video input
fails and the user is asked for Artiscan's JSON export. The experimental
`BrowserArtiscanExtractor` and a future owned OCR implementation share this
port, so browser automation is visible and replaceable rather than hidden
infrastructure.

### Experimental Artiscan browser adapter

The adapter has two distinct network phases:

1. **Bootstrap without user data.** A persistent Chromium profile may issue
   only same-origin `GET` requests while the pinned Artiscan build and its static
   PWA assets load. Foreign origins, WebSockets and non-GET requests are blocked
   and recorded.
2. **Offline processing with user data.** The whole browser context is switched
   offline before the video is assigned to the file input. Artiscan then
   decodes, OCRs and exports GOOD locally.

The current adapter automates the two pinned Artiscan checkpoints. When the
exact transcoding prompt appears it clicks the unique `No` action. Artiscan may
remember that choice and skip the prompt; this is accepted only when the next
pinned `Configure` control is uniquely visible. Uploaded files
are decoded by Artiscan through WebCodecs and rendered as `ImageData` on a
canvas; there is no HTML video element to observe. During scanning, GrindLess
samples the current canvas, the modal's remaining-progress bar and catalogue
count. It accepts natural completion, stops after a sustained black tail, or
recovers a populated stream that remains at least 98.5% with no activity for
ten seconds. An open `Artifact Correction` dialog owns the stop action;
otherwise the unique action inside `Running Scan` owns it. Page-wide ambiguous
matches are never used. After stopping, the adapter requires unique enabled
`View Artifacts` and `Download JSON` controls. The audit records the performed
actions, observed trigger and `scan_stop_control`. Missing or ambiguous UI fails
closed. The normal app uses headless Chromium; the CLI can show it for debugging.
The macOS Gatekeeper approval still happens before Python starts and therefore
remains in the launcher runbook rather than the extraction audit.

The resulting JSON is untrusted until `import_good` validates it. The adapter
does not own GOOD schema interpretation and cannot return partial success. A
changed build, unexpected UI, failed auto-calibration, zero artifacts or bad
JSON stops the import. Direct JSON remains the fallback.

`good_compare` is the eval boundary for a video whose reference export is
known. It compares validated artifact multisets rather than raw JSON bytes:
artifact and substat ordering do not matter, numeric spelling is normalized,
and an omitted `location`/`lock` is equivalent to GOOD's default empty/false
value. Set, slot, rarity, level, main stat, every substat key/value, equipped
location and lock state are part of the core signature. Metadata and harmless
serialization differences are reported separately.

Calibration is stored only in the local persistent browser profile and can be
reused for a compatible resolution. The video itself is not persisted by the
adapter. Playwright is optional, so the simulator and JSON import have no
browser dependency.

### Local video-import job

The graphical application exposes video first and direct GOOD JSON second. A
multipart upload never leaves loopback: `VideoImportService` streams it into a
private temporary directory, starts one background Artiscan worker and returns a
job identifier. The UI polls the typed job state instead of holding a request
open during the multi-minute automatic scan. The job exposes its current phase,
last update and decoded-video progress. The narrow populated near-end recovery
runs after ten idle seconds; other inactivity fails after 90 seconds, and an
eight-minute overall deadline bounds the import. Every worker error preserves
its failed phase and cause. A second concurrent scan fails visibly.

The write endpoint requires `X-GrindLess-Local: 1` in addition to the Host
allowlist. This non-simple header forces a foreign browser origin to preflight;
the application grants no CORS access. On success, the validated GOOD payload is
held only in process memory long enough for the current UI to run the existing
audit. The raw temporary video is deleted on success and failure. This is a
single-local-user lifecycle, not the future authenticated server queue.

### Extraction performance evidence

Every new browser extraction is wrapped by `ProcessTreeProfiler`. A monotonic
clock measures the session runner from browser startup through bootstrap, video
decoding, OCR, automatic checkpoint handling and GOOD export. The value is
end-to-end extraction latency, not pure OCR compute time. Every 100 ms,
the profiler records both the Python process RSS and the sum of RSS across
Python plus all descendants,
which includes the Playwright driver and Chromium worker processes.

The process-tree value is the primary operational memory metric. It may count
shared pages more than once and can miss a spike shorter than the sampling
interval, so it is not presented as unique physical memory. The report includes
the interval, sample count, completeness flag, warnings and the exact metric
description. If the process monitor cannot identify the current Python process,
the browser extraction fails loudly rather than emitting a plausible but false
number. `psutil` belongs only to the optional `browser` dependency group.

The macOS launcher stores each run in a UTC-timestamped directory. This makes a
30-run P50/P95 dataset append-only instead of overwriting `run-report.json`.

## Stable ports

### Local application boundary

`application.analyze_character_inventory` owns the orchestration from untrusted
GOOD payload through strict import, a versioned character goal and empty-baseline
audit. `application.simulate_character_farm` freezes that audit's five selected
artifact IDs, narrows the goal to user-selected slots and runs the real agent
through the seeded simulator. Mavuika-specific wrappers remain only as a
compatibility contract. These services return typed, UI-ready results without
importing FastAPI or React.

`EnkaClient` is a consent-gated profile-evidence adapter, not an artifact
inventory adapter. It honors Enka response TTL and parses only character,
talent and weapon evidence for the bundled 116-character Genshin 7.0 roster.
The roster is a dated local snapshot so an upstream future or internal entry
cannot silently appear in the UI. `EnkaCollectionRegistry` combines several partial
showcases and retains the collection in process memory for 30 minutes. Its mode
is immutable. In the default `discovery` mode it imports every catalog-known
profile visible in each snapshot and remains incomplete until the user submits
a final `TeamIntent`; finalization then proves that every required member or
candidate was observed. The alternate `planned` mode reports an exact
predeclared checklist and completes when no expected character is missing. The
registry stores an HMAC binding and the last four UID digits, never the full
UID. Artiscan/GOOD remains the only authority for the full artifact inventory.

`POST /api/v1/profiles/enka/snapshots` accepts either discovery snapshots without
a team intent or planned snapshots with one. Discovery is completed only by
`POST /api/v1/profiles/enka/collections/{collection_id}/finalize`. Reusing a
collection under another mode or finalizing with an unobserved target, manual
member or candidate fails loudly before any model call.

`TeamEvidenceTool` projects only the requested Enka collection into the first
strategic model call. It includes character identity, locally curated role when
available, observed level/constellation/talents and weapon identifiers,
level/refinement, plus the team modes, two independently selected objectives,
their versioned definitions, explicit candidate keys and user
preferences. Full UID, video, GOOD and artifacts are excluded. Generic roster
entries are marked `identity_only`. Live web research may cover current public
kit and role knowledge, while the audit continues to distinguish it from local
versioned evidence.

`TeamStrategist` requires a strict `TeamStrategyDraft` JSON object containing
separate candidate lists. The user chooses Luna, Terra or Sol and Low, Medium or
High reasoning. The provider receives the schema through the Responses API
structured-output field as well as a required web-search tool. The normal output
budget is 6,000 tokens. A syntactically detectable cutoff is recorded as
`invalid_output` and permits exactly one recovery call with an 8,000-token cap.
For an automatic decision the model must compare at least two distinct
compositions whenever the pool permits more than one.

`TeamEvaluator` is the single owner of the comparative quality rubric. It uses
model-researched finite 0–5 claims but applies local, versioned weights and
thresholds for damage potential, reaction coherence, rotation stability,
energy feasibility, comfort, account readiness and domain compatibility. The
domain evidence names all locally allowed target sets so web research can cover
their current enemies and restrictions before the later artifact step chooses
one exact set. The weights differ for `max_dps`, `comfort` and `stable_rotation`.
Hard gates reject unverified
mechanics, mechanically incoherent or energy-infeasible teams, objective-specific
minimum failures, out-of-pool/unobserved characters, changed manual teams and
explicit nearby exclusion phrases in the user comment. The result stores all
candidate scores, weighted points, evidence and rejection reasons. It explicitly
sets `exact_dps_claimed: false` because this is a ranking rubric, not a combat
simulator. If no target/domain pair passes, the first output is invalidated and
the same model receives one quality retry containing the evaluator's reasons.
A second failure stops visibly.

`TeamStrategyValidator` then rechecks the selected pair, changed user objectives,
the preference explanation and same-team constraints. Automatic domain teams
are selected independently from the declared pool and may exclude the target character. A
shared composition may have different target/domain objectives; the LLM must
explain that compromise rather than letting one objective overwrite the other.
The UI receives the validated
plan, exact transmitted text, exact model output, provider response identifier,
token totals and optional price. Provider, quota, parsing and validation errors
fail the strategy endpoint visibly; they do not silently replace the plan with
a template. The user may instead continue to artifact analysis without a team
strategy call.

`ArtifactEvidenceTool` is the second strategic projection. It never transmits
the raw GOOD document, UID or video. It includes the confirmed target/domain
teams, target Enka fields, the GOOD weapon key when present, versioned 4pc and
optional 2pc+2pc set options, character-specific main/substat vocabularies,
profile provenance, contextual caveats and non-binding benchmarks, compact
inventory counts and up to six representative observations per slot. Missing
weapon/character evidence, content-only comparison and unresolved ER
breakpoints are explicit limitations in the prompt and result.

`ArtifactGoalPlanner` asks the model for exactly five slots, one curated set
composition option,
ordered main-stat choices, one global ordered substat list and a complete slot
priority. `ArtifactGoalValidator` converts ordering into deterministic weights,
enforces rollable stats, the target profile's exact main-stat vocabulary and
allowed composition choices, and reruns
`BruteForceBuildOptimizer.audit_initial_build`. That audit chooses all five
items jointly, enforces either 4pc or 2pc+2pc and identifies the exact flexible
fifth artifact. Reward analysis uses the same global constraint and can move
the flex slot through coordinated replacements. The accepted goal is
`shadow_only`, but the teaching simulator consumes it rather than silently
falling back to the old static profile. Only a detectably truncated JSON answer
is retried once through the shared structured-output recovery helper.

`data/target_profiles.json` is a separate, versioned local knowledge source.
It covers 56 playable limited five-stars plus four starter targets for the 7.0
snapshot. Each entry contains role, two practical four-piece choices, optional
curated 2pc+2pc choices, ordered main/substats, a guide URL and date, caveats
and optional advisory benchmarks.
Startup validates coverage and identity against the Enka-derived roster.
Benchmarks remain `enforced: false`; ER is not considered proven until the
rotation layer can validate energy and timing. Set options resolve into global
`set_requirements`; the model cannot introduce a combination absent from the
profile.

`RotationEvidenceTool` is the third strategic projection. It includes only the
confirmed domain team, bounded Enka combat fields, an optional compact artifact
goal and explicit knowledge limitations. `RotationPlanner` asks the model for
semantic actions rather than key bindings or timings. `RotationValidator`
preserves the four-person team, requires every member to participate, rejects
actions outside the fixed allowlist and requires a declared unavailable-burst
policy for every burst step. It compiles the accepted draft into ordered primary
and recovery states whose failed confirmations always transition to `safe_stop`.

The compiled rotation remains `structural_only`, `shadow_only` and has
`input_authority: none`: current public cooldown, energy, reaction and rotation
knowledge is researched through the provider web tool and its sources are
audited, but particles in the current fight, animation timing, hit confirmation
and enemy state are not observed authoritative inputs. The server
revalidates state ordering, coverage, transitions, recovery structure, terminal
states and a content fingerprint before accepting a rotation in a simulation.
The fingerprint also covers the model explanation, assumptions and stop
conditions so the stored session remains reconstructable. No rotation state is
dispatched to `GameAdapter` in version 0.25.

`web_app` is a loopback-only HTTP adapter over those services. The React
frontend may select a file, choose target slots, policy, resin budget and a
reproducible simulator seed, but it cannot redefine scoring, close a slot, or
interpret GOOD fields. The simulation response groups domain trace evidence by
reward claim for presentation. Invalid and empty documents return an explicit
422 response. Raw GOOD JSON stays in memory. Completed simulation payloads,
without the input inventory, are written to a local SQLite history. The same
database contains an atomic successful-call quota ledger and token totals, but
never an API key. The server binds to `127.0.0.1`, restricts accepted Host
headers to loopback/localhost and grants no CORS access to external origins.

`POST /api/v1/team-strategies` is the first strategic endpoint. It accepts a
team intent, an in-memory Enka collection identifier, one configured OpenAI
provider, Low/Medium/High reasoning and optional preferences. The server resolves evidence from the registry; the
browser never posts Enka profiles back as self-asserted facts. The response is
non-executable and explicitly reports `decision_owner: llm_plus_team_evaluator` and
`execution_status: shadow_only`.

`POST /api/v1/rotation-strategies` accepts a confirmed team intent, the in-memory
Enka collection identifier, an optional validated artifact goal, a configured
provider and optional preferences. It returns the exact draft, compiled states,
structural validation, evidence limitations and LLM audit. The browser may pass
the compiled result into the teaching simulation, where it is revalidated and
recorded as `not_executed`; the endpoint grants no input authority.

Every provider-backed narration report carries the exact configured model,
provider response identifier, returned input/cached/output token counts, session
totals and an optional cost estimate. Pricing is keyed to the exact model: the
default Luna tariff is pinned to the dated public price observation, while an
unknown model remains unpriced unless complete rates are configured. The
provider's billing ledger remains the authority.

The production frontend bundle is served by the same process, while Vite uses a
development proxy. This web boundary is intentionally compatible with a future
Tauri shell; desktop packaging does not own domain behavior.

### `FarmAdapter`

- `resin_remaining`
- `claim_reward(cost) -> RewardBatch`
- `enhance_artifact(artifact, target_level) -> EnhancementResult`

`ArtifactDomainSimulator` implements this port now. A future `GameAdapter`
must return the same validated domain objects. Its internal map navigation,
screen classification, input and OCR do not leak into the agent.

### `BuildOptimizer`

- evaluates a complete five-artifact build;
- enforces global stats and set constraints;
- searches the best eligible build;
- evaluates every target slot against the frozen baseline;
- compares main stat, set and desired substat types without looking at their
  numeric values in the default mode;
- uses actual rolled numbers only in the explicitly authorized enhancement mode.

The current brute-force implementation is exact for small test inventories. It
can later be replaced by candidate pruning or another solver.

### `Narrator` and strategic LLM

- emits a checkpoint explanation;
- emits a final explanation.

The offline template implementation keeps farm-explanation tests deterministic.
Luna, Terra and Sol own the bounded strategic decisions described above, while
artifact arithmetic and the currently implemented stop thresholds remain typed
tool decisions until the later ADR 0024 loops are delivered.

`LLMProvider`, `SQLiteQuotaStore`, and `SQLiteSessionStore` isolate operational
concerns from the agent. The local demo accepts an OpenAI Responses API provider
or an OpenAI-compatible Qwen endpoint. Every attempted narration records the
exact transmitted text, whether the provider was actually called, token usage,
output or error. A provider failure degrades to the deterministic template; a
quota or configuration failure before a call sends nothing.

On macOS the OpenAI key is read from Keychain by the launcher. Windows/Linux
use their normal environment or secret-store integration. A server rollout can
replace these adapters with authenticated per-user services without changing
the domain decision loop or simulation response contract.

## Stop-policy invariants

1. Baseline mode is explicit. `equipped` freezes the observed equipped build;
   `empty` first selects a provisional item for every available slot and keeps
   unsatisfied slots as farm goals. Missing equipment is never invented.
2. Default mode never predicts `+0 -> +20` rolls. It accepts only an observed
   candidate with a suitable main stat/set and better desired substat *types*
   than the baseline; artifact substat numbers do not participate.
3. Enhancement is a separate capability. It is disabled by default and requires
   a positive artifact limit plus a target level. Only then may actual observed
   rolled values participate in the comparison.
4. `spend_all` never stops because of an early good drop; it analyzes after the
   complete allowed batch.
5. `economy` evaluates each confirmed reward and stops only after every target
   slot has a promising candidate.
6. A guaranteed alternative can produce `change_goal` only in `economy` mode.
7. Observation confidence below `0.95` or an unconfirmed reward produces
   `safe_stop` before the observation affects the inventory.
8. Resin deducted by an attempted claim remains visible in the result even if
   observation fails.

## Empty-baseline audit

`BruteForceBuildOptimizer.audit_initial_build` is the entry point for an
artifact-only export when the target character wears nothing. It ranks only
items with an allowed set and main stat. Ordering uses:

1. declared main-stat priority;
2. desired substat *types* and their build priorities;
3. number of useful types;
4. number of observed starting substats;
5. source order for a deterministic tie.

Substat values never break a tie. A provisional item can fill a slot without
closing its farm goal. For example, an ATK% goblet may make a starter build
possible while a preferred Pyro DMG goblet remains pending.

Simulation accepts the audit even when that provisional selection is partial or
cannot yet satisfy its 4pc/2pc+2pc requirement. The frozen baseline is therefore
a partial `Build`: absent slots have no artifact ID and are never represented by
synthetic placeholder items. A qualifying observed drop is compared with score
zero for an absent slot. When the complete set signature is unreachable, the
joint optimizer retains the state with the greatest verified progress toward
the required composition instead of rejecting the session. This behavior is
defined by ADR 0030.

## Explainability

Every session returns ordered `TraceEvent` records covering:

- chosen policy, frozen artifact IDs and explicitly empty baseline slots;
- staged rewards;
- retained candidates and any explicitly authorized enhancements;
- accepted and pending slots at every checkpoint;
- the final decision and stop reason.

The local UI's run timeline is a projection of these trace records. Economy
mode shows one checkpoint per confirmed reward plus the final explanation;
spend-all mode shows staged rewards and one final batch decision. This count is
the LLM-call boundary when an external narrator is selected. The offline
narrator reaches the same checkpoints without API calls. Economy mode therefore
uses up to one call per obtained reward plus one final explanation; spend-all
uses one final explanation after the complete batch.

Local history persists the response projection and narration audit, not the raw
inventory. It is deliberately a one-user store; server identity and shared
budget enforcement remain deployment concerns.

## Boundary for the future real adapter

The experimental adapter must add stricter preconditions than the simulator:

- exact game-window identity and focus;
- known screen state with confidence at least `0.95`;
- postcondition after every high-level action;
- hard transition and time limits;
- user-controlled emergency stop;
- no memory access, traffic interception, injection, anti-cheat interaction,
  concealment, artifact destruction, or Primogem spending.

These rules are adapter preconditions. Failure is returned as an untrusted or
unconfirmed observation, and the existing agent already converts that to
`safe_stop`.
