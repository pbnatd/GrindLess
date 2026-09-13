# ADR 0016: Target Linux/X11 for the first game-control adapter

- Status: accepted
- Date: 2026-09-09
- Supersedes: the first-target and Linux-execution parts of [ADR 0006](0006-separate-portable-core-from-platform-game-adapters.md)

## Context

ADR 0006 kept direct Linux execution unavailable and named Windows as the first
planned shadow-adapter target. The first available test machine will instead run
Genshin through An Anime Game Launcher on Linux. The product also needs real
environment interaction to demonstrate a capability beyond inventory-only
optimizers.

An Anime Game Launcher is unofficial and runs the game through Wine. HoYoverse
also identifies automation scripts and mouse macros as unauthorized tools. An
external OS-input implementation therefore cannot be represented as ban-safe,
even when it avoids injection, memory reads, file modification and traffic
interception.

X11 exposes a tractable, inspectable window capture and input boundary. Wayland
intentionally restricts global capture and input and would require a separate
permission and portal design. Supporting both in the first adapter would hide
materially different safety and failure modes behind one Linux label.

## Decision

Linux/X11 is the first direct-control target. The controlled reference setup is:

- one visible Genshin window launched through An Anime Game Launcher;
- X11 session with `DISPLAY` available;
- borderless 1920x1080 game client area and English game UI;
- GrindLess installed as a native user process outside the launcher's Flatpak;
- `xdotool` for bounded OS input and `maim` for window capture.

The implementation is split into two authorities:

1. `LinuxGameAdapter` probes and reports environment evidence. Probing never
   focuses the game and never sends input.
2. `LinuxX11GameControl` captures the verified window and sends only allowlisted
   input after explicit operator arming.

Input is disarmed by default. Every mutating action must re-check the exact
window ID, foreground focus and 1920x1080 geometry. A persistent stop file or a
pointer in the top-left fail-safe corner stops before an input event. Ambiguous
windows and unknown geometry fail closed.

The adapter never launches the game, enters credentials, bypasses anti-cheat,
injects into Wine/the game process, reads process memory, modifies game files or
intercepts network traffic. The user launches and signs in manually.

This record authorizes only the probe, capture and guarded-input foundation. It
does not mark autonomous dungeon navigation, combat, reward recognition or the
`FarmAdapter` implementation complete. Those capabilities need screen-state
fixtures and a live evaluation on the reference setup.

## Consequences

- The static capability matrix reports Linux execution as `experimental`, with
  the incomplete route stated explicitly.
- The application can show exactly which environment precondition failed.
- Development can proceed without a live Linux game by testing command and
  fail-closed behavior with a fake command boundary.
- Wayland, Windows and macOS require separate adapters rather than conditional
  branches inside the X11 implementation.
- No documentation or UI may describe the Linux path as safe from account
  sanctions.
