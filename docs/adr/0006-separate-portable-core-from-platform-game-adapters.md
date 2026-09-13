# ADR 0006: Separate the portable core from platform game adapters

- Status: accepted
- Date: 2026-09-08

## Context

The first design draft described GrindLess as a Windows desktop application.
That bundled together two different capabilities: analyzing an exported
inventory and controlling a running Genshin client. The user develops and tests
on macOS, while future users may use Windows or Linux computers and may play on
a console or mobile device.

The simulator, GOOD importer, optimizer, stop policy and browser-local Artiscan
flow do not depend on the Genshin process. Playwright supports Chromium on
macOS, Windows and Linux. Direct game observation and input are different: they
depend on an available game client, OS permissions, windowing APIs and a
separate safety evaluation.

Calling the whole product unsupported on macOS would unnecessarily restrict
the useful analysis path. Calling direct execution cross-platform would hide an
unimplemented and potentially unsafe capability.

## Decision

GrindLess has three explicit portability layers:

1. The deterministic core, simulator, GOOD import and optimizer are portable
   across macOS, Windows and Linux.
2. Video extraction is an experimental local-browser capability on those same
   desktop systems. Packaging must obtain a compatible local Chromium and run
   the same strict Artiscan build, network and validation checks.
3. Game observation and input live only in OS-specific `GameAdapter` plug-ins.
   No plug-in may be inferred from the host OS. Windows is the first planned
   shadow adapter target; macOS and Linux execution are unavailable until each
   has an explicit implementation, official-client assessment and safety eval.

Console and mobile accounts can participate through a companion workflow: the
player records or exports inventory material and processes it on a supported
desktop. GrindLess is not installed inside PlayStation or Xbox, and direct
mobile execution is outside the MVP.

`platform_support` owns the runtime capability matrix. Unknown hosts and absent
adapters report `unavailable`; they never silently downgrade an execution
request to a guessed implementation.

## Consequences

- macOS becomes a first-class development and analysis platform immediately.
- Windows is no longer a prerequisite for the Artiscan E2E evaluation.
- The project can package the same core for macOS, Windows and Linux while
  keeping platform-specific permissions and failures isolated.
- A user can analyze an account played on a console or phone through a desktop
  companion, but cannot ask the desktop process to control that console or
  phone.
- Local Qwen packaging remains platform-specific: Metal is the intended Apple
  Silicon path, while CUDA is the intended NVIDIA path. Both require measured
  builds before being advertised as available.
- The existing simulator-first and explicit Artiscan boundaries remain
  unchanged.
