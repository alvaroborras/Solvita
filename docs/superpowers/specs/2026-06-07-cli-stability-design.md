# CLI Stability Design

Date: 2026-06-07
Topic: AlgoPilot CLI minimum-viable stability pass

## Goal

Stabilize the current AlgoPilot CLI so it works as a **lightweight terminal companion** to the main agent, similar in spirit to a simplified dashboard:

- users can start a run from the terminal
- users can provide input in the three current ways
- users can see the most important live stages
- users get understandable failures when startup or solve execution goes wrong

The priority is **basic correctness and reliability**, not feature parity with the dashboard.

## Current Problems

The current CLI already has a usable visual shell, but several logic bugs make it unreliable:

1. Input and output paths do not follow one consistent resolution rule.
2. Interactive path entry treats relative paths incorrectly.
3. Invalid numeric flags such as `--max-iterations abc` fail late and unclearly.
4. The CLI swallows many backend startup/execution failures and degrades to a vague “Process exited without a final event.”
5. The backend verifier stage is not represented in the CLI’s routed progress model.
6. Paste-description mode writes temp input files without cleanup.
7. Test coverage is too thin to protect any of the above behavior.

## Product Positioning

The CLI will remain a **simple live solve monitor**, not a full analytical interface.

### Keep

- interactive entry point
- file picker mode
- manual path mode
- paste-description mode
- live progress UI
- final verdict UI
- token summary and run metadata

### Simplify / Explicitly Not Build

- no replay mode
- no persisted run history
- no evidence workbench
- no failure analysis surface
- no dashboard-style session management
- no attempt to render every backend artifact event

## Success Criteria

The CLI is considered fixed when all of the following are true:

1. `algopilot solve some/problem.json` resolves the input path correctly.
2. `-o out.cpp` behaves predictably and consistently with input path semantics.
3. Interactive manual path mode resolves relative paths correctly from the user’s shell context.
4. Invalid `--max-iterations` values fail immediately with a clear CLI error.
5. Backend startup and early process failures are surfaced as meaningful terminal errors.
6. `verifier_phase` is shown in the CLI’s live stage model.
7. Paste-description runs do not leave behind unbounded temp files.
8. Focused CLI tests cover the fixed behaviors.

## Design Summary

The existing visual structure will be preserved:

- `Header`
- `Arena`
- `Duel`
- `Verdict`
- `InputMode`

The implementation change is to **tighten the control plane around them**:

- normalize option resolution before launching the UI
- validate user inputs before spawning Python
- improve backend process event/error handling
- minimally extend stage routing to include verifier
- add lifecycle cleanup for ephemeral paste-mode inputs

## Behavioral Decisions

### 1. Path semantics

CLI path behavior will be unified:

- **input file paths**: resolve relative to `process.cwd()`
- **output file paths**: resolve relative to `process.cwd()`
- **interactive typed paths**: resolve relative to `process.cwd()`
- **file-picker paths**: already absolute, pass through unchanged

Rationale:

- this matches normal CLI expectations
- it avoids the current split behavior where input follows shell cwd but output silently goes to repo root
- it keeps the repo root as an implementation detail rather than a user-facing path base

### 2. Python executable behavior

The CLI will continue to accept a caller-provided Python binary and pass it through as-is.

No auto-discovery changes are required in this pass because:

- `run_algopilot.sh` already provides the recommended path
- the current bug set is not caused by interpreter selection

### 3. Error model

The CLI should distinguish these failure classes:

- invalid CLI arguments
- invalid input path / unreadable file
- backend process spawn failure
- backend exits before streaming any meaningful event
- backend emits explicit `error` event
- backend exits after partial progress but before `final`

User-facing behavior:

- argument or path problems should fail **before** launching the Ink solve view when possible
- backend failures during a solve should show a specific message in the terminal, not only a generic missing-final fallback

### 4. Stage model

The CLI will explicitly show these high-level stages:

- `abstract_phase`
- `testgen_phase`
- `solver_skill_plan`
- `codegen_phase`
- `verifier_phase`
- `hacker_phase`

Display rules:

- `abstract`, `testgen`, `solver_skill_plan`, `verifier` belong to the simplified pre/post pipeline track
- `codegen` remains the iterative “defender” track
- `hacker` remains the “attacker” track

The verifier does not need an elaborate new visual metaphor. It only needs to be visible and not silently omitted.

### 5. Paste-description lifecycle

The CLI will keep using a temp JSON file as an adapter to the existing backend input shape, but it must own cleanup.

The temp file should be deleted when:

- the solve process finishes normally
- the solve process errors
- the CLI unmounts before completion

## Module-Level Changes

### `cli/src/index.tsx`

Responsibilities after this change:

- parse flags
- validate `--max-iterations`
- resolve input and output paths consistently relative to `process.cwd()`
- pass normalized options into the app

Expected changes:

- add a small normalization/validation helper layer
- reject `NaN`, zero, and negative iteration counts with a direct CLI error

### `cli/src/App.tsx`

Responsibilities after this change:

- own the temporary file lifecycle for paste-description mode
- pass a cleanup callback or temp-file metadata into solve mode

Expected changes:

- store whether the current solve input is ephemeral
- ensure temp file cleanup happens exactly once on terminal exit / solve completion

### `cli/src/hooks/useSolver.ts`

This file is the main stability target.

Responsibilities after this change:

- spawn backend process
- parse NDJSON events
- track whether any meaningful event was received
- surface process failures clearly
- clean up ephemeral temp inputs

Expected changes:

- attach explicit `error` and `exitCode/signal` handling
- detect “no final event” versus “backend already told us the failure”
- expose clearer reducer actions for process failure
- include verifier stage mapping in reducer routing

### `cli/src/types.ts`

Expected changes:

- expand event/stage types if needed for verifier display
- add any small process-status typing needed for better error handling

### `cli/src/components/InputMode.tsx`

Expected changes:

- no UI redesign
- keep current three modes
- manual path submission should send raw user input upward, but the parent/controller path handling must be unambiguous and tested

### `cli/src/components/Arena.tsx` / `Duel.tsx`

Expected changes:

- minimal or none
- only enough adjustment to reflect verifier visibility cleanly

## Testing Strategy

This pass needs actual logic tests, not just a single helper test.

### Required new tests

1. input path normalization from cwd
2. output path normalization from cwd
3. invalid `--max-iterations` rejection
4. interactive paste mode temp file cleanup behavior
5. reducer / event handling includes `verifier_phase`
6. backend premature exit yields a meaningful CLI error state

### Verification commands

- `cd cli && npm test`
- `cd cli && npm run build`
- `cd cli && node bin/algopilot.js --help`
- at least one targeted Python-side smoke path through `run_algopilot.sh --help` if wrapper behavior is touched

## Non-Goals

This pass does **not** attempt to:

- redesign the visual CLI layout
- add replay/history features
- mirror dashboard artifact panels
- change backend event schema
- refactor the dashboard
- rewrite the CLI around a different state architecture

## Risks and Mitigations

### Risk: fixing path semantics breaks users who relied on repo-root output

Mitigation:

- choose standard CLI semantics and document them
- add tests so behavior is explicit and stable

### Risk: process error handling becomes too noisy

Mitigation:

- only surface concise user-facing messages
- keep raw stderr inheritance behavior unless it directly corrupts UX

### Risk: temp-file cleanup races with backend reads

Mitigation:

- cleanup only after process close / unmount cleanup
- do not delete the temp file immediately after spawn

## Implementation Boundary

This is a **stability pass**, not a CLI redesign.

The code should become:

- more predictable
- easier to understand
- better tested

without broadening scope beyond the minimum features a user needs to run the agent from the terminal and follow progress live.
