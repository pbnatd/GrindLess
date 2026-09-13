# ADR 0010: Put the local UI behind an application API

- Status: accepted
- Date: 2026-09-09

## Context

The simulator, GOOD importer, optimizer, stop policy and Artiscan adapter are
Python components with explicit contracts. The first user-facing application
must work on macOS, Windows and Linux, remain visually flexible, and later add
video import, simulated farming and interchangeable Qwen/Luna narration.

Placing domain decisions in frontend components would duplicate authority and
make the command-line and graphical paths disagree. Binding the domain directly
to a desktop shell would make early testing and later packaging unnecessarily
coupled.

## Decision

Add a local application layer with three replaceable parts:

1. `application.py` owns use-case composition over the existing domain modules
   and returns typed Pydantic projections.
2. A versioned FastAPI adapter exposes those use cases only on
   `127.0.0.1`. The browser parses a selected JSON file and sends it to the
   local process; the first slice does not persist the payload. Accepted Host
   headers are restricted to loopback/localhost and external origins receive no
   CORS permission.
3. A React/TypeScript frontend owns presentation and interaction only. It maps
   enum keys to user-facing Russian labels but cannot decide whether an
   artifact closes a goal.

The first vertical slice is `GOOD JSON -> Mavuika preset -> initial build
audit`. Video import, farm-session execution and LLM narration extend the same
application API later. A Tauri shell is packaging, not a new owner of domain
logic, and is deferred until the local web flow is stable.

## Consequences

- CLI and GUI use the same GOOD validation and optimizer rules.
- The frontend can be redesigned or replaced without moving domain logic.
- The local API becomes a versioned contract and needs endpoint/schema tests.
- The browser talks only to the loopback backend in this slice; no API key or
  game credential is placed in frontend code.
- Running the interface requires optional FastAPI dependencies and a built
  frontend. Desktop installers remain future work.
