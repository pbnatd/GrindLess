# GrindLess Agent

Simulator-first MVP of an agent that farms Genshin Impact artifacts until a
declared goal is met. The simulator is behind the same `FarmAdapter` boundary
that a future, explicitly enabled `GameAdapter` will implement.

The current version does not yet run an autonomous Genshin farming route. Its
portable core is a reproducible environment for testing artifact goals, GOOD
imports, optional enhancement, resin policies, explanations, and safe stops;
the first Linux/X11 plug-in adds a separately gated observation/input boundary.

Version 0.35.0 adds the first real Linux farming observation slice without
granting input authority. The operator records checksummed local references for
seven screen states, and a calibrated classifier accepts a state only at
similarity `>=0.95` with a `>=0.02` lead over another state. A shadow runner
observes a manually played route, validates its transition graph and stores the
exact local PNG, hash, confidence and reference behind every state. Unknown or ambiguous frames,
illegal transitions, the emergency stop file, more than 12 transitions or five
minutes stop the run. Only a confirmed reward screen counts as success;
`input_authority` remains `none`.

Version 0.34.1 lets a farm simulation start from a partial or invalid artifact
baseline. Missing suitable slots remain absent instead of being filled with
synthetic artifacts; the first candidate satisfying the declared set, main-stat
and useful-substat contract can close that selected slot. A complete imported
baseline is still frozen when one exists.

Version 0.34.0 adds `TeamEvaluator` between researched model proposals and the
accepted team plan. For automatic selection the model must return distinct
alternatives when the confirmed pool permits them. A deterministic rubric then
applies objective-specific weights for damage potential, reaction coherence,
rotation stability, energy feasibility, comfort and account readiness. Hard
gates reject unverified mechanics, incompatible reaction/energy claims,
out-of-pool or unobserved characters, changed manual teams and explicit user
exclusions such as “не использовать Беннета”. If no pair passes, the rejected
reasons are sent to the same model for one quality retry; a second failure is
shown instead of accepting a weak composition. The UI exposes every score,
weighted contribution, rejected candidate and evidence statement. The score is
a comparative decision rubric, not a fabricated exact DPS calculation.

Version 0.33.0 keeps the top liquid-glass navigation and Brick Ember / Air
Force Blue palette, fixes the last purple hover-state leak and hardens every
card grid against horizontal viewport overflow. Strategic planning now offers
Luna, Terra or Sol with Low, Medium or High reasoning. Team, artifact and
rotation calls require live web search, preserve provider citations in the
audit and fail instead of presenting an unresearched answer as current game
knowledge. The user's optional comment is a binding planning input: each
accepted response must explain how it was applied or why it conflicts with a
hard constraint. Automatic domain planning is independent of the target team
and does not require the target character. Artiscan also accepts the pinned
state in which the saved no-transcode preference skips the question and moves
directly to `Configure`.

Version 0.32.0 kept the top liquid-glass navigation introduced in 0.31.0 but
returned the interface to its Brick Ember / Air Force Blue palette. Red now
marks the active action and blue carries depth, status and glass highlights.
All 60 supported target profiles use bundled 256×256 character portraits
resolved from the versioned roster `avatar_id` through Enka's Genshin metadata;
the initial-letter placeholder is no longer rendered. These assets remain
local during the demo instead of being fetched at page render time. Their
source mapping is the EnkaNetwork API-docs `store/gi/avatars.json`; game artwork
ownership remains with its respective rights holders and must be reviewed
before public distribution.

Version 0.31.0 replaced the fixed sidebar with a top liquid-glass navigation
dock. At rest it shows one linear icon per workflow step; hovering or focusing
an icon expands only that item to reveal its title and status. Compact and
touch layouts keep the icon rail horizontally scrollable without hover-only
interaction. The visual system uses pearl glass surfaces, animated atmospheric
fields, a slow dock glint and a faint
vertical `GRIND / LESS` background wordmark. Motion honors
`prefers-reduced-motion`, no human photography is bundled, and all
existing workflow and safety states remain visible. Wide application surfaces
stay constrained to the viewport. The target-character catalog remains a
compact disclosure with search, bounded independent scrolling and a stacking
layer above the following glass panels. Choosing a target closes the menu
without changing the target-selection contract. By default the application asks the user to place
desired characters in the public Enka showcase, combines one or
more snapshots and only then collects two separate team intents from the
observed pool. The previous full-roster search remains an explicit alternative.
Both paths later combine Enka evidence with a locally extracted Artiscan/GOOD
artifact inventory. A versioned local database now contains complete artifact
profiles for all 56 currently playable limited five-stars plus Xiangling,
Noelle, Kaeya and Lisa. Each profile records its guide source and observed date,
role, curated four-piece and optional two-piece-combination choices,
character-specific main stats, ordered substats, contextual caveats and any
non-binding stat benchmark.
The team selector contains all 116 playable characters in the bundled Genshin
7.0 roster snapshot; announced and internal Enka entries are excluded.
Before artifact import, GPT Luna or a local Qwen can now own the first strategic
decision: selecting permitted target/domain teams and explaining their synergy,
weak points and priorities from a minimal typed Enka projection. After GOOD
import, a second audited model call chooses a curated set, legal main stats,
ordered substat priorities and a slot order for the confirmed team. Deterministic
validators preserve manual teams, reject invented characters, sets and stats,
and re-audit the local inventory against the model-owned goal. A third audited
call now creates a semantic domain rotation for the confirmed team. A local
validator compiles it into explicit states, requires a fallback for every burst
and routes every unconfirmed action to `safe_stop`. All three results are
shadow-only and cannot reach game input. The UI shows the provisional five-slot
build, the LLM goal, ranked candidates, semantic rotation and pending goals. It
does not reimplement artifact decisions: it calls a loopback FastAPI adapter
over the same deterministic Python application service used by tests.

## Implemented vertical slice

- Strict Pydantic models for artifacts, builds, goals, rewards, decisions, and traces.
- A seeded artifact-domain simulator with 200 Original Resin and 20 per reward.
- Simplified five-star artifact generation. New drops remain at their observed
  level by default; the simulator can enhance only after explicit authorization.
- Default candidate comparison uses main stat, set, and desired substat types.
  Numeric substat values and hypothetical future rolls are deliberately ignored.
- An exact brute-force optimizer for small MVP inventories.
- Per-slot goals for flower, plume, sands, goblet, and circlet.
- Global build constraints such as ER and required set pieces.
- Two resin policies:
  - `spend_all`: collect every allowed reward, then analyze one batch;
  - `economy`: analyze after every reward and stop when every target slot passes its threshold.
- A separate `change_goal` decision when a guaranteed weapon/talent upgrade has
  higher configured gain per resin.
- Safe stop when reward confirmation fails or observation confidence is below `0.95`.
- An in-memory evidence trace for every important state transition.
- Offline `TemplateNarrator` behind the future Qwen/Luna narration boundary.
- Artiscan/GOOD v1–v3 JSON import with typed characters, weapons, equipped
  locations, talents and v3 inactive substats; unknown versions and duplicate
  equipped items fail loudly.
- One normalized inventory-input boundary: a ready GOOD-compatible JSON works
  now; raw video can use an explicitly selected experimental local-browser
  Artiscan extractor and otherwise fails with an explicit message.
- The browser extractor pins the observed Artiscan build, allows only
  same-origin static GETs during bootstrap, switches Chromium offline before
  assigning the video, captures the locally generated GOOD download and records
  a network audit. The current integration chooses `No` when the pinned
  transcoding prompt appears; if Artiscan has remembered that choice, the
  unique visible `Configure` step is accepted instead. It then detects the
  black tail or media end and presses `Stop Scan` automatically.
- An empty-baseline inventory audit for a character with no equipped artifacts.
  It selects a provisional item for every available slot and separately reports
  which slot goals are actually satisfied.
- A versioned catalog with all 116 playable Genshin 7.0 team candidates and
  60 complete artifact targets: every currently playable limited five-star and
  four accessible starter/free characters. Search keeps the expanded target
  picker usable; Mavuika remains a reproducible compatibility demo.
- Separate target-team and domain-team intents. For each team the user
  independently chooses `max_dps`, `comfort`, or `stable_rotation`. The choice
  applies to both manual analysis and automatic selection. When both views use
  one composition, neither objective silently replaces the other: the model
  must explain the compromise and the validator preserves both values.
- Explicit manual-team or candidate-pool input. One audited strategic LLM call
  may choose both teams from the collected Enka evidence; manual compositions
  cannot be changed and automatic choices cannot leave the declared pool.
- A typed evidence-builder → LLM → validator loop with strict JSON output and
  visible prompt, response, cited web sources, reasoning level, token and cost
  audit. Luna, Terra and Sol use a Responses API JSON
  Schema format. The normal strategy budget is 4,000 output tokens; a response
  that is detectably cut off is marked invalid and retried once with 6,000.
  Other invalid model output fails loudly instead of being silently repaired.
- A second typed artifact-goal loop after GOOD import. It sends a compact
  projection rather than the raw inventory: confirmed teams, target evidence,
  the equipped weapon key when GOOD provides it and at most six observations
  per slot. The model chooses one versioned 4pc or 2pc+2pc composition option,
  legal main stats, ordered substat priorities and slot priority. The validator
  rebuilds a `FarmGoal`, re-audits GOOD locally, selects the exact flex item and
  passes that goal to the teaching simulator. Future rolls, ER breakpoints and
  damage gains are never invented.
- Target main stats now come from `data/target_profiles.json`, not broad
  element-level legality. The model also receives profile sources, caveats and
  advisory benchmarks; numeric guide values never become universal hard gates.
- Artifact set requirements are global build constraints: one 4pc set or two
  distinct 2pc sets. A dynamic program jointly selects all five artifacts from
  the complete local GOOD inventory, reports the exact flexible fifth item and
  can move that flex slot when coordinated replacements improve the build.
  Nilou's versioned profile includes the first curated 2pc+2pc HP option.
- A third typed rotation loop. The model owns the semantic order and reasoning,
  while `RotationValidator` preserves the confirmed domain team, limits actions
  to skill/burst/normal/charged/dodge, requires every member to participate and
  requires an explicit recovery policy for every burst. The compiled plan,
  explanations, assumptions, stop conditions and SHA-256 fingerprint are stored
  with the simulation and revalidated by the server before reuse.
- Rotation validation is deliberately `structural_only`: current cooldowns,
  energy, reactions and published sequences are researched on the web, but
  live particle generation, animation timing, hit confirmation and enemy state
  are not observed. The resulting plan has `input_authority: none`,
  `execution_status: blocked` and is never sent to the game adapter.
- Consent-gated Enka profile loading with TTL-aware caching and exact missing
  character feedback. The default discovery flow imports every known character
  visible in the showcase, permits repeated snapshots and requires the user to
  explicitly finalize the collection before strategy. The full-roster-first
  flow remains available for an exact predeclared checklist. Both modes merge
  snapshots into one 30-minute in-memory collection without persisting the full UID.
- Selectable offline narration, Luna/Terra/Sol strategic Responses API and
  local OpenAI-compatible Qwen narration behind one provider contract. The
  model now owns team strategy, artifact
  goals and a structurally validated rotation; checkpoint decisions remain the
  next ADR 0024 slice.
- A local SQLite quota ledger (40 successful calls/day, 400/month by default),
  exact prompt/token audit and reproducible session history. The raw GOOD input
  and API key are not stored in that database.

The simulator probabilities are teaching approximations and are not claimed to
be official drop rates. All probability tables live inside the adapter so they
can be calibrated without changing the agent.

## Platform support

Windows is not required for inventory analysis. The current Python core and
GOOD import work on macOS, Windows and Linux; the Playwright/Artiscan video path
is experimental on all three. Run the capability check instead of inferring
support from the operating system:

```bash
grindless-platform
```

| Capability | macOS | Windows | Linux |
|---|---|---|---|
| Simulator and GOOD analysis | available | available | available |
| Local Artiscan video import | experimental | experimental | experimental |
| Local Qwen | external endpoint: Metal/CPU | external endpoint: CUDA/CPU | external endpoint: CUDA/CPU |
| Direct game execution | unavailable | planned, not implemented | experimental X11 probe/capture/guarded input; farming route pending |

PlayStation, Xbox and mobile recordings can later enter through a desktop
companion, but the agent is not installed on those devices and does not control
them. Direct phone execution is outside the MVP.

## Run locally

Python 3.12 and Pydantic 2 are required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
grindless --policy economy --seed 42
```

On macOS or Linux, the `source` command above activates the environment. On
Windows PowerShell, use:

```powershell
.venv\Scripts\Activate.ps1
```

Run the full-budget policy:

```bash
grindless --policy spend_all --seed 42
```

Print the complete explainability trace:

```bash
grindless --policy economy --seed 42 --json
```

Run tests without extra test dependencies:

```bash
python -m unittest discover -s tests -v
```

When running directly from a source checkout without installation:

```bash
PYTHONPATH=src python -m grindless --policy economy
```

### Local graphical application

Build the React frontend and install the optional local API:

```bash
cd frontend
npm install
npm run build
cd ..
pip install -e '.[app,browser]'
playwright install chromium
grindless-app
```

Open <http://127.0.0.1:8765>. Upload an MP4, MOV, MKV or WebM recording from the
inventory screen. GrindLess starts Artiscan in a local headless browser, declines
transcoding, stops at the black tail or media end, validates the generated GOOD and
opens the build automatically. The temporary video is deleted after success or
failure. A JSON file whose root declares `"format": "GOOD"` remains the direct
fallback. Both inputs go only to the loopback backend. The application then
selects the provisional build for the chosen supported character,
configure target slots and a 20–200 resin budget, and run either economy or
spend-all through the seeded simulator. It renders every synthetic reward,
comparison result and stop reason. Offline mode makes no cloud request. Session
results and LLM-call audits are saved locally in
`~/.grindless/grindless.sqlite3`; the raw GOOD JSON is not persisted. An invalid
or empty GOOD document fails visibly instead of producing a partial profile.
For provider-backed explanations the result screen shows the exact model,
response IDs, returned input/output token totals and a cost estimate. The
default `gpt-5.6-luna` estimate uses the public OpenAI tariff observed on
2026-09-09; a differently configured model remains unpriced unless complete
rates are supplied.

The default onboarding asks the user to place desired characters in Character
Showcase and import Enka first. Further snapshots can be merged after the Enka
cache TTL when the showcase has too few slots. The application never treats one
showcase as the complete account: the user explicitly finalizes discovery, then
selects exact teams from observed profiles or lets the model choose from that
observed pool. A second onboarding method preserves the full 116-character
search and derives a predeclared showcase checklist.

After either Enka path is complete, the onboarding screen can make one strategic
Luna, Terra or Sol call before video import. The user also selects Low, Medium
or High reasoning; Astra and levels above High are intentionally absent. The
request contains only the selected
character/team modes, the explicit candidate keys, selected Enka
character/weapon fields and optional user preferences. Live web search is
required for current kits, reactions, team guides and rotations, and cited
sources are shown in the audit. It contains no UID, video, GOOD document or
artifacts. “Continue without strategy” preserves the
deterministic/offline path. A successful plan is shown with its validation and
full provider audit before the user proceeds.

After GOOD import, “Сформировать цели агентом” makes the second strategic call.
The prompt contains only the confirmed team, target/weapon evidence, legal
set/stat vocabularies, compact counts and at most six observations per slot.
The returned five-slot goal is validated, used to re-audit the local inventory
and then passed to the teaching simulator. The raw GOOD document is not part of
the model request. A basic deterministic profile remains an explicit fallback.

The simulator freezes the five selected inventory items before the session.
Economy mode checks after every reward and can stop when all chosen slots have
their first qualifying improvement; spend-all stages every reward and analyzes
once after the budget. The default seed `386` is a reproducible teaching run for
the supplied 108-item Mavuika fixture. Change it to explore a different drop
sequence. Synthetic probabilities are not official drop rates, and artifact
enhancement is always off in this screen: no `+0 -> +20` rolls are invented.

On macOS, the committed frontend bundle means Node.js is not needed for normal
use: double-click `scripts/run_grindless_app_macos.command`. The launcher creates
`.venv`, installs the local API plus Playwright Chromium and opens the application in the default
browser. Keep its Terminal window open; `Control-C` stops the server. If macOS
blocks the downloaded command file, allow that specific file through **System
Settings → Privacy & Security → Open Anyway** and launch it again.

To enable the OpenAI API narrator on macOS, first double-click
`scripts/configure_openai_key_macos.command`, enter an OpenAI Platform API key,
and restart the main launcher. The helper stores the secret in macOS Keychain
under `GrindLess OpenAI API`; it is never written to the project or SQLite.
Gatekeeper may require **Open Anyway** for this helper too.

For frontend development, run the API on port 8765 and `npm run dev` in the
`frontend` directory. Vite proxies `/api` to the loopback API.

### Linux game-control foundation

Linux/X11 is the first direct-control target. Version 0.35 can inspect the
environment, find exactly one 1920x1080 Genshin window, capture it, calibrate
local screen-state references and validate a manually played route in shadow
mode. The lower-level driver can issue an explicitly armed allowlisted input
event, but the route observer never uses that authority. It does not yet
navigate, fight or collect a live reward. The UI shows this distinction on the
**Управление** screen.

The reference setup is Ubuntu 24.04 LTS in an **Ubuntu on Xorg** session, An
Anime Game Launcher from Flathub, borderless 1920x1080 Genshin with English UI,
and native GrindLess outside Flatpak. Install and run the app with:

```bash
./scripts/run_grindless_app_linux.sh
./scripts/check_linux_game_setup.sh
```

Input is disarmed by default. It needs `GRINDLESS_ENABLE_GAME_INPUT=1` for a
single supervised command; focus loss, geometry drift, the top-left pointer
fail-safe or `~/.grindless/STOP_GAME_INPUT` stops before input. This is not a
ban-safety guarantee: An Anime Game Launcher and gameplay automation are
unofficial. Full setup and emergency-stop instructions are in the
[Linux/AAGL runbook](docs/runbooks/linux-aagl-game-control.md).

Record a user-confirmed state and then observe a manually played route without
input:

```bash
.venv/bin/grindless-linux-game --record-state overworld_ready
.venv/bin/grindless-linux-game --observe-state
.venv/bin/grindless-linux-game --shadow-run --interval 1
```

Calibrate all seven states listed in the runbook before treating a shadow result
as route evidence.

Validate an Artiscan JSON export and select its equipped Xiangling build:

```bash
grindless-good examples/xiangling.good.json --character Xiangling
```

Run the simulator against that imported inventory:

```bash
grindless --good examples/xiangling.good.json --character Xiangling --policy economy --seed 42
```

The import keeps all artifacts, including unequipped ones. GOOD stores the main
stat key but not its derived numeric value, so imported main values remain
unknown. This does not affect the default content-only comparison. Unknown GOOD
slot or stat keys fail loudly instead of being guessed.

`JSON` and `GOOD` are not competing formats. JSON is the file syntax; GOOD is
the inventory schema inside it. An Artiscan file such as `artifacts.json` with
`"format": "GOOD"` is already a GOOD-compatible JSON and can be passed to
`grindless-good` unchanged.

The product flow is `video -> inventory extractor -> validated GOOD -> agent`.
It is now wired into the graphical application as a background local job; the
user does not handle the intermediate GOOD file. Direct JSON upload remains the
reliable fallback. Artiscan does not
expose a documented video-upload API; its current PWA performs FFmpeg and OCR
work in the browser. The experimental adapter automates that local flow behind
`VideoInventoryExtractor`, so a future owned OCR implementation can replace it
without changing the optimizer or agent.

Install the optional browser dependency and its Chromium runtime:

```bash
pip install -e '.[browser]'
playwright install chromium
```

These commands are the same on macOS, Windows and Linux after activating the
virtual environment. Playwright downloads the browser build for the current OS
and CPU architecture; it is not copied between platforms.

For a macOS E2E run, double-click
`scripts/run_artiscan_macos.command`. The launcher checks the host and Python
version, installs the project and local Chromium inside `.venv`, opens a native
file picker and runs Artiscan visibly. On success it creates a timestamped
directory under `artiscan-e2e-result/` containing `extracted.good.json` and
`run-report.json`, then prints wall time and peak Python-plus-Chromium RSS. The
raw GOOD is written only after extraction and strict validation succeed, and
later runs do not overwrite earlier measurements.

On the first launch, macOS may block the downloaded script. Open **System
Settings → Privacy & Security**, find the blocked launcher, choose **Open
Anyway** and confirm; then start it again. Do this only for the launcher from
the verified project archive. Do not disable Gatekeeper system-wide.

The pinned Artiscan UI checkpoints are automatic. The adapter requires the exact
transcoding question and clicks **No**. After non-black video content, it clicks
**Stop Scan** on a sustained black tail; if no tail exists, it uses the media
end. Missing or ambiguous controls fail the import instead of guessing.

These steps and troubleshooting notes are preserved in the dedicated
[macOS Artiscan runbook](docs/runbooks/macos-artiscan-video-import.md).

Run a local video import and apply the Mavuika preset:

```bash
grindless-good inventory.mp4 --artiscan-browser --preset mavuika
```

The first compatible video is auto-calibrated with Artiscan's own detector and
the result is retained in a dedicated local browser profile. Add
`--artiscan-headful` to observe the automated browser flow while debugging.
The current Artiscan scanner expects clear English UI text and recommends at
least 1080p input. A changed build, incompatible resolution, failed calibration,
zero detected artifacts or invalid GOOD output stops the import.

Before the video file is assigned, the adapter takes the browser context
offline. This is stricter than merely assuming the current site will not upload
the file: the scan cannot make a network request after it receives the video.

Evaluation status: the representative 1920x880, 55-second recording completed
the local macOS video-to-GOOD path. The new export contains 108 artifacts and
all 108 exactly match the reference by set, slot, rarity, level, main stat,
substats, location semantics and lock state. Artiscan added an explicit empty
`location` field that the older export omitted; GOOD defines both as unequipped.
The first instrumented operator-assisted run took 257.024 seconds, with a peak
process-tree RSS of 1,619,673,088 bytes (1,544.6 MiB) and peak Python RSS of
51,052,544 bytes (48.7 MiB). This is one observation, not P50/P95, and its wall
time includes the user's response time at the Artiscan checkpoints. New runs
also record the sampling interval, sample count and measurement warnings. See
[the successful macOS evaluation](docs/reports/artiscan-e2e-video-eval-2026-09-09.md).

Reproduce the structural comparison with:

```bash
grindless-good-compare artifacts.json extracted.good.json
```

The command validates both inputs, ignores artifact and substat ordering,
normalizes numeric spelling and exits nonzero if any artifact content is
missing, added or changed.

Audit an artifact-only Artiscan export for the unequipped Mavuika preset:

```bash
grindless-good artifacts.json --preset mavuika --top 3
```

The command reports both a provisional selection and `pending_slots`.
For an empty baseline, a slot closes only when a preferred main stat has at
least two useful observed substat types. Numeric substat values and hypothetical
future rolls are not used. ATK% and Elemental Mastery sands intentionally have
equal main-stat priority until an enhanced build and rotation calculator can
resolve their tradeoff.

The simulator does not require that selection to contain five suitable pieces
or already satisfy the final 4pc/2pc+2pc composition. Existing candidates are
frozen by ID; missing slots stay empty. If the required composition is not yet
available, joint selection maximizes observed progress toward it while each
selected farm slot remains open until a qualifying candidate is observed.

## Optional API narrators and local quotas

OpenAI API access is separate application authentication; a ChatGPT subscription
is not an API credential or API budget. Create a Platform project key and keep
it in a secret store or the `OPENAI_API_KEY` environment variable. The configured
model ID defaults to `gpt-5.6-luna`, but model availability is account-specific;
override it with `GRINDLESS_OPENAI_MODEL` if the API rejects that ID.

```bash
GRINDLESS_OPENAI_MODEL='your-enabled-model-id' grindless-app
```

For a local OpenAI-compatible Qwen server:

```bash
GRINDLESS_QWEN_BASE_URL='http://127.0.0.1:8000/v1' \
GRINDLESS_QWEN_MODEL='Qwen/Qwen3-8B' grindless-app
```

The local ledger defaults to 40 successful calls per UTC day and 400 per UTC
month for the single local user. Failed provider attempts are audited but do
not consume that successful-call allowance. Economy mode can make one call
after each obtained reward plus one final call; spend-all makes one final call.
This is why the number of calls depends on actual progress rather than a fixed
two-call estimate.

Direct local access is appropriate for the single-computer demonstration. A
multi-user release replaces the local provider/ledger/session-store adapters
with authenticated server implementations and a shared subscription cap; the
agent and UI-facing contracts remain unchanged.

## Enhancement permission

`FarmGoal.enhancement` is disabled by default. Enabling it requires both an
explicit `max_artifacts` limit and a target level. Only content-promising
candidates may consume that budget. Without the permission, the agent never
calls `FarmAdapter.enhance_artifact`.

## Current demos

The fixture uses Xiangling with a four-piece Emblem of Severed Fate baseline.
The target slots are plume and circlet. This is only demo data: the domain
models and agent do not contain character-specific branching.

The initial expected-gain estimator is explicit configuration rather than a
pretend probability model. A later milestone will replace it with calibrated
Monte Carlo simulation and preserve the same interface.

The artifact-only import demo uses Mavuika C2 with Wolf's Gravestone R1 and a
four-piece Obsidian Codex target. It does not invent equipped artifacts when the
export has no `location` fields.

## Next milestones

1. Collect timestamped performance reports across at least 30 repeated runs and
   a small video corpus, then calculate P50/P95 wall time and peak RSS.
2. Implement the strategic LLM orchestrator and deterministic team-evaluation
   tool over the explicitly imported candidate pool and publish its evidence.
3. Implement a `RotationValidator` that compiles a model-proposed domain
   rotation into a finite-state, recoverable action plan.
4. Replace the configured expected-gain value with calibrated estimation.
5. Add optional enhancement checkpoints at `+4/+8/+12/+16`, including fodder
   and Mora budgets and a confirmation gate.
6. Package and measure a concrete local Qwen runtime for Metal/CUDA/CPU.
7. Run the same agent against recorded reward batches and screen-state fixtures.
8. Collect and evaluate real Linux screen-state references with the implemented
   observation-only shadow runner.
9. Only after shadow evals pass, implement a separately enabled experimental
   adapter for one fixed domain and one fixed rotation.

See [architecture.md](docs/architecture.md) for the boundaries that make the
simulator replaceable.
