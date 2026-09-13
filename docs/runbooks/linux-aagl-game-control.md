# Linux/X11 and An Anime Game Launcher setup

## What this setup enables

Version 0.35 adds a calibrated shadow observer to the Linux game-control
foundation. It can record operator-confirmed screen references and verify a
manually played route through the reward screen without sending input. Dungeon
navigation, combat and reward collection are still not claimed as working.

The launcher and gameplay automation are unofficial. This setup does not make
an account safe from sanctions. Use a separate low-value test account only if
you accept that risk. GrindLess does not bypass anti-cheat or read game memory.

## Reference environment

- Ubuntu 24.04 LTS, x86-64.
- **Ubuntu on Xorg** session (`XDG_SESSION_TYPE=x11`).
- An Anime Game Launcher installed from Flathub.
- Genshin in borderless 1920x1080 with the English UI.
- One monitor for the first calibration.
- GrindLess runs natively outside Flatpak.

X11 is a deliberate first-version requirement. Wayland input and screen capture
use a different permission model and are not silently treated as X11.

## Install the desktop and launcher dependencies

On Ubuntu 24.04:

```bash
sudo apt update
sudo apt install flatpak xdotool maim python3.12 python3.12-venv
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub moe.launcher.an-anime-game-launcher
```

Log out. On the login screen select the gear icon and **Ubuntu on Xorg**, then
log in again. Verify the session:

```bash
echo "$XDG_SESSION_TYPE"
```

The expected value is `x11`.

## Install and open GrindLess

From the GrindLess directory:

```bash
./scripts/run_grindless_app_linux.sh
```

The first run creates a local Python environment, installs the application and
Playwright Chromium, then opens `http://127.0.0.1:8765`. Keep the terminal open.

Inventory video processing remains the first step in the application. The
**Управление** screen separately shows the Linux adapter checks.

## Prepare the game window

1. Start An Anime Game Launcher and launch Genshin manually.
2. Sign in manually; GrindLess never handles credentials.
3. Set the game language to English.
4. Set display mode to borderless and resolution to 1920x1080.
5. Close any second game or splash window.
6. Focus the Genshin window.
7. Run:

```bash
./scripts/check_linux_game_setup.sh
```

`Status: ready` means observation is ready. It does not enable input.

## Calibrate screen states

Keep input disabled. Manually open each state in the game, return to the
terminal and record it. The game window must remain focused when the command
captures it.

```bash
.venv/bin/grindless-linux-game --record-state overworld_ready --note "logged in, HUD visible"
.venv/bin/grindless-linux-game --record-state map_open
.venv/bin/grindless-linux-game --record-state domain_entrance
.venv/bin/grindless-linux-game --record-state party_setup
.venv/bin/grindless-linux-game --record-state combat
.venv/bin/grindless-linux-game --record-state reward_prompt
.venv/bin/grindless-linux-game --record-state reward_screen
```

The PNG files and their checksummed manifest are stored locally in
`~/.grindless/game-state-references`. More than one reference per state is
allowed and useful when the same UI has legitimate visual variation.

Test one current frame:

```bash
.venv/bin/grindless-linux-game --observe-state
```

An exit code of `2` means the frame was unknown, below `0.95` confidence or too
close to another calibrated state. It must not be relabelled automatically.

## Observation-only route

Start the observer, then play the supported domain manually:

```bash
.venv/bin/grindless-linux-game --shadow-run --interval 1
```

The JSON trace records every screenshot hash, confidence and state change. The
same local run directory under `~/.grindless/game-shadow-runs` retains every
sampled PNG so an `unknown` result can be inspected and calibrated instead of
guessed. These images are not uploaded automatically and may contain the UID
visible in the game interface. A confirmed `reward_screen` is the only
successful terminal state. Unknown or
illegal transitions, the stop file, more than 12 transitions, or five minutes
stop the observation. The command never sends input and cannot be combined with
`--click` or `--press`.

## Supervised input gate

Input requires an explicit environment flag for that single terminal command.
For the first calibration, use only an allowlisted harmless key while the game
window is focused:

```bash
GRINDLESS_ENABLE_GAME_INPUT=1 .venv/bin/grindless-linux-game --press e
```

Before sending the event, GrindLess re-checks the foreground window and its
geometry. If either changed, no input is sent.

## Emergency stop

Either move the pointer into the top-left corner before the next action, or
create the persistent stop file:

```bash
mkdir -p ~/.grindless
touch ~/.grindless/STOP_GAME_INPUT
```

To permit a later supervised test, remove exactly that file:

```bash
rm -- ~/.grindless/STOP_GAME_INPUT
```

The stop file is checked before every mouse or keyboard event.

## Expected failures

- `setup_required`: wrong session, missing `DISPLAY`, `xdotool` or `maim`.
- `game_not_running`: no visible window named `Genshin Impact`.
- `needs_attention`: duplicate window or a size other than 1920x1080.
- `ready`: capture is available; input still depends on explicit arming.

Unknown or ambiguous state is a stop condition, never an instruction to guess.
