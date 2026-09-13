# ADR 0031: Calibrate screen states before Linux shadow runs

- Status: accepted
- Date: 2026-09-11
- Extends: [ADR 0016](0016-target-linux-x11-for-the-first-game-control-adapter.md)

## Context

ADR 0016 established a guarded X11 capture and input boundary but deliberately
did not define dungeon-state recognition. A live farming route cannot safely be
built from guessed coordinates or screenshots captured on a different display,
Wine build, language or UI scale. The development environment also has no
access to the operator's live Linux game window.

Before any route is allowed to issue input, GrindLess needs reproducible local
evidence for the exact reference setup and a way to evaluate the observer
without conflating recognition with control.

## Decision

The first Linux farming slice is a calibrated, observation-only shadow run.
The operator manually opens each supported state and records one or more trusted
1920x1080 PNG references for:

- overworld ready;
- map open;
- domain entrance;
- party setup;
- combat;
- reward prompt;
- reward screen.

References are stored under `~/.grindless/game-state-references` with a
versioned manifest, capture timestamp, state label, optional operator note and
SHA-256 checksum. `unknown` is never a recordable reference.

The classifier compares a current capture with the local calibrated reference
set. A state is confirmed only when its similarity is at least `0.95` and its
lead over the best different state is at least `0.02`. Missing references,
checksum changes, low confidence and ambiguous matches remain explicit unknown
states.

`ShadowGameObserver` samples the verified focused X11 window and accepts only a
declared state-transition graph. It records every observed frame hash,
confidence, matched reference and transition. The exact sampled PNG files and
the final JSON trace are retained under `~/.grindless/game-shadow-runs`; they
remain local and are never uploaded automatically. It stops without input on an
unknown state, illegal transition, operator stop file, more than 12 transitions
or five minutes. A shadow run succeeds only when the reward screen is
confirmed. Its result always reports `input_authority: none`.

Calibration and shadow observation cannot be combined with mouse or keyboard
arguments in one CLI invocation. This ADR does not authorize navigation,
combat, reward claiming or implementation of `FarmAdapter`.

## Consequences

- The next live work can collect real fixtures before route coordinates or
  combat timings are encoded.
- Failures preserve evidence instead of silently choosing the closest state.
- Similarity thresholds are a provisional MVP classifier contract and must be
  evaluated on the operator's recorded corpus before any supervised route is
  armed.
- The first fixed-domain executor remains a later, separately gated change.
