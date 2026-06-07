# CLI Command Mode Design

Date: 2026-06-07
Topic: Pre-solve CLI command mode for session-scoped runtime parameter updates

## Goal

Add a small set of built-in CLI commands, available only **before solving starts**, so users can change a few core runtime parameters from inside the AlgoPilot terminal UI in a Claude-Code-like way.

The first version only needs to cover the most basic knobs:

- model
- max iterations
- python executable
- output path

These commands should affect the **current CLI session defaults**, not repository config files or global environment.

## User Intent

The user wants a lightweight in-CLI way to tweak the most important solve settings without leaving the interface or editing YAML by hand.

This is not a request for a large command language or a persistent settings system.

## Scope

### In Scope

- a new pre-solve `Command` tab in the input interface
- slash-style commands entered in that tab
- session-scoped updates to:
  - `model`
  - `maxIterations`
  - `pythonBin`
  - `output`
- visible current-session configuration summary in the command view
- clear success/failure feedback after each command

### Out of Scope

- commands during an active solve
- persistent settings saved to disk
- editing `config/models.yaml`
- editing environment variables
- model discovery / autocomplete
- command history
- fuzzy parsing
- advanced runtime flags
- replay, dashboard features, or post-run controls

## Product Positioning

This feature should feel like a small command palette inside the existing CLI, not like a full shell.

It is intended to answer:

- “Use a different model for this session.”
- “Bump max iterations before I run the next problem.”
- “Use this Python binary instead.”
- “Write the next output somewhere else.”

It is not intended to become a general-purpose terminal command system.

## Interaction Model

The command feature is available only in the **pre-solve input UI**.

The input UI currently has three tabs:

- `Select problem file`
- `Enter file path`
- `Paste description`

This feature adds a fourth:

- `Command`

Behavior:

- users switch to `Command` with the same tab-switching model as the other modes
- users enter one slash command on a single line
- pressing `Enter` executes the command
- the command updates the current CLI session defaults
- the command does **not** start solving
- the user then switches back to `Select`, `Path`, or `Paste` and starts a solve using the updated defaults

## Supported Commands

First version supports exactly these:

- `/model <name>`
- `/max-iterations <positive-int>`
- `/python <path-or-binary>`
- `/output <path>`
- `/show`
- `/reset`

### Command semantics

#### `/model <name>`

Stores the provided model string as the session default model for subsequent solves.

Validation:

- argument must be non-empty

#### `/max-iterations <positive-int>`

Stores the provided positive integer as the session default iteration cap.

Validation:

- must be a positive integer
- must follow the same numeric rules as the CLI argument parser

#### `/python <path-or-binary>`

Stores the provided Python executable string as the session default backend interpreter for subsequent solves.

Validation:

- argument must be non-empty
- path is accepted as a string and resolved using the existing CLI path rules if relative
- no eager filesystem existence check is required in command mode

#### `/output <path>`

Stores the provided output path as the session default output path for subsequent solves.

Validation:

- argument must be non-empty
- relative paths resolve from the current shell directory

#### `/show`

Prints or refreshes the current session configuration summary.

#### `/reset`

Restores the command-managed fields to the CLI session’s original startup defaults.

## Command Parsing Rules

The first version should be strict and simple.

Rules:

- commands must start with `/`
- one line = one command
- no multiple commands per line
- no quoting language beyond basic whitespace splitting unless already trivial to support
- unknown commands return a clear error
- malformed commands return a usage-style error

Examples:

- valid: `/model gpt-4.1-mini`
- valid: `/max-iterations 8`
- invalid: `model gpt-4.1-mini`
- invalid: `/temperature 0.2`
- invalid: `/model`

## Session State Semantics

The command updates apply to the **current CLI session only**.

That means:

- they are kept in memory while the CLI process is alive
- they affect future solves launched from the same CLI session
- they do not modify:
  - `config/models.yaml`
  - environment variables
  - repository files
- they disappear when the CLI exits

This is the correct default because it gives users fast control without side effects on the project or machine.

## Path Semantics

The command mode must reuse the same path semantics already stabilized in the CLI:

- relative paths resolve from `process.cwd()`
- absolute paths are used as-is

This applies to:

- `/python ./venv/bin/python`
- `/output ./my_solution.cpp`

The command mode must not introduce a second path-resolution rule.

## UI Design

### New tab

Add a `Command` tab beside the existing three tabs.

### Inside the Command tab

The tab should show:

1. a one-line command input area
2. a short help block listing the supported commands
3. a current session configuration summary
4. the most recent success or error feedback message

### Current configuration summary

Show the currently active session defaults for:

- `model`
- `maxIterations`
- `pythonBin`
- `output`

This should be easy to scan so the user can confirm what the next solve will use.

### Feedback behavior

After pressing `Enter`:

- on success: show a concise success message
- on failure: show a concise error message

Examples:

- `model updated: gpt-4.1-mini`
- `max iterations updated: 8`
- `unknown command: /temperature`
- `usage: /model <name>`

Command failures must **not** mutate the current session defaults.

## Architecture

This feature should be implemented with a small, separate command layer rather than baking command parsing into `InputMode.tsx`.

Recommended structure:

- `cli/src/components/InputMode.tsx`
  - owns tab switching
  - renders the new `Command` tab alongside existing modes

- `cli/src/components/CommandMode.tsx`
  - UI for command entry
  - shows command input
  - shows current configuration summary
  - shows latest feedback

- `cli/src/commandState.ts`
  - pure command execution logic
  - parses command text
  - validates arguments
  - returns:
    - updated session defaults on success
    - unchanged state plus error message on failure

- `cli/src/commandState.test.ts`
  - unit tests for command parsing and session updates

- `cli/src/App.tsx`
  - owns session-scoped defaults state
  - passes current defaults and updater callback into `InputMode`

- `cli/src/solveOptions.ts`
  - reused for path resolution and numeric validation

## State Model

The CLI app should own a session-defaults object containing the fields relevant to future solves:

- `model`
- `maxIterations`
- `pythonBin`
- `output`

The command layer updates this in memory.

Then:

- picker mode solve uses these defaults
- path mode solve uses these defaults
- paste mode solve uses these defaults

The command layer should not need to know anything about the running solve UI.

## Error Handling

### User-facing validation errors

Return direct, readable messages for:

- command without `/`
- unknown command
- missing command argument
- invalid integer
- empty path

### Non-mutating failure rule

If command execution fails:

- current session defaults stay unchanged
- error feedback is shown

### No eager backend validation

Do not try to verify model existence or python executability during command parsing.

Those are runtime concerns.

The command layer should stay fast and deterministic.

## Testing Strategy

### Required unit tests

For `commandState.ts`:

- `/model` updates model
- `/max-iterations` updates iteration count
- `/python` updates python path
- `/output` updates output path
- `/show` returns current config
- `/reset` restores initial defaults
- unknown command returns error
- missing argument returns usage error
- invalid integer returns error
- non-slash input returns error

### Required path tests

Reuse or extend `solveOptions.ts` path tests so command-updated paths follow the same cwd semantics.

### Required component-level tests

Minimal tests only:

- `Command` tab renders current configuration summary
- successful command feedback is shown
- failed command feedback is shown

No heavy TUI snapshot coverage is required for first version.

## Non-Goals

The first version will not support:

- `/base-url`
- `/temperature`
- `/api-key`
- command autocomplete
- command history
- live mutation during a running solve
- persistence to disk
- multi-command scripting

These can be added later only if usage proves they are needed.

## Success Criteria

This feature is complete when:

1. The pre-solve input UI has a working `Command` tab.
2. `/model`, `/max-iterations`, `/python`, and `/output` update current-session defaults.
3. `/show` and `/reset` work.
4. Invalid commands produce clear messages and do not change state.
5. The updated defaults are actually used by the next solve launched from picker/path/paste mode.
6. Path semantics remain consistent with the stabilized CLI behavior.
7. Tests protect the new command behavior.

## Recommended Initial Behavior Summary

This first version should feel like:

- a **small command panel**
- only available **before** solving
- used to tweak **session-scoped defaults**
- safe, strict, and easy to understand

That is the smallest design that satisfies the user’s request without dragging the CLI into an overbuilt command language.
