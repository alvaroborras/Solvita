# Dashboard Run Control And History Design

Date: 2026-06-07
Topic: Add interrupt control for active solves and deletion for completed run history

## Goal

Extend the dashboard so users can:

1. interrupt an in-progress solve without losing the run record
2. delete a completed run record from the dashboard history, including its persisted backend files

The design must preserve backend/frontend consistency and keep the run lifecycle semantics explicit.

## Scope

### In Scope

- interrupting a currently running dashboard solve
- persisting interrupted runs as ended runs with final status `cancelled`
- deleting completed run history entries from the dashboard UI
- deleting the corresponding persisted backend run JSON and `index.json` entry together
- confirmation UI before deleting a run
- frontend session cleanup when the currently opened replay run is deleted
- focused backend and frontend tests for these behaviors

### Out of Scope

- deleting a currently running run directly
- auto-deleting interrupted runs
- retry/restart actions for existing runs
- bulk deletion of run history
- arbitrary retention policies or pagination for run history
- custom JavaScript scrollbar or unrelated dashboard layout work

## Current Problems

### 1. No interrupt control for live solves

The backend already has a low-level `cancel()` method on `SolveProcess`, but the dashboard exposes no user-facing way to stop a run once it starts.

Current consequence:

- if the user no longer wants the current problem, they must wait for the solve to finish on its own

### 2. Run deletion is incomplete and inconsistently exposed

The backend already has `DELETE /api/runs/{run_id}`, but it is not wired into the frontend and its semantics are too weak.

Current consequence:

- users accumulate more and more run history over time
- there is no UI to remove obsolete completed runs
- the current delete endpoint does not explicitly protect against deleting an active run

### 3. Frontend session state can outlive deleted records

The current frontend session model can restore and replay persisted runs. If a run is deleted after being opened, the UI must not continue pointing to a missing `runId`.

## Product Requirements

### Interrupt Behavior

- `Interrupt` is available only for the current live run
- interrupting a run must end it with final status `cancelled`
- interrupted runs remain visible in history and can later be replayed or deleted
- interrupting should be idempotent from the user’s perspective:
  - once the request is in flight, the button becomes pending/disabled
  - repeated clicks should not create duplicate lifecycle transitions

### Delete Behavior

- `Delete` is available only for completed runs
- clicking `Delete` must first open a confirmation dialog
- deletion must be permanent for the persisted dashboard record
- deletion must remove:
  - the run’s JSON file under `dashboard/data/runs/`
  - the corresponding summary row in `dashboard/data/runs/index.json`
- deleting a run that is currently opened in replay mode must clear the current session and return the UI to idle

### Consistency Rules

- active runs cannot be deleted
- completed runs cannot be cancelled
- cancellation and deletion must each have explicit backend endpoints with explicit state rules
- frontend state must be driven from backend truth rather than guessed locally

## Recommended Approach

Use two distinct control flows with separate endpoints:

1. `POST /api/runs/{run_id}/cancel`
2. `DELETE /api/runs/{run_id}`

This is the recommended approach because:

- the user already defined different lifecycle rules for interrupt vs delete
- the semantics stay explicit and easy to debug
- the backend can enforce state-specific restrictions cleanly
- the frontend can present state-specific controls without hidden branching logic

## Rejected Alternatives

### 1. One polymorphic “manage run” endpoint

Example: one endpoint that cancels active runs and deletes completed runs based on current state.

Rejected because:

- the same action would mean different things depending on timing
- backend logs and client error handling become less obvious
- accidental destructive behavior is easier to introduce later

### 2. Interrupt and immediately remove the run

Rejected because:

- the user explicitly wants interrupted runs preserved
- it destroys useful forensic information about why the solve was stopped
- it couples two actions that should remain independent

### 3. Delete support for running runs

Rejected because:

- the user explicitly scoped delete to completed history only
- “delete while running” collapses interruption and deletion into one ambiguous operation

## Backend Design

### API Changes

#### New: `POST /api/runs/{run_id}/cancel`

Behavior:

- if the run does not exist:
  - return `404`
- if the run exists but is not currently running:
  - return `409`
- if the run is running:
  - terminate the subprocess
  - finalize the run as `cancelled`
  - persist the finished run into the event store
  - broadcast completion to live subscribers
  - return success metadata

Response shape should include at least:

- `run_id`
- `cancelled: true`
- `final_status: "cancelled"`

#### Tighten existing: `DELETE /api/runs/{run_id}`

Behavior:

- if the run is currently active in `ProcessManager` and still running:
  - return `409`
- if the persisted run does not exist:
  - return `404`
- otherwise:
  - delete the persisted run file
  - remove the corresponding item from `index.json`
  - return `deleted: true`

This endpoint remains only for completed persisted runs.

### `SolveProcess.cancel()` semantics

The current low-level `cancel()` is not sufficient because it only terminates the subprocess and marks in-memory state as cancelled.

It must be upgraded to behave like a real run finalization path:

1. terminate the subprocess if still alive
2. append a synthetic terminal event with `type: "final"` and `status: "cancelled"`
3. set:
   - `self.final_status = "cancelled"`
   - `self.completed_at = now`
   - `self.status = "completed"` or an equivalent ended state that still serializes as final status `cancelled`
4. persist with `EventStore.save_run(...)`
5. broadcast:
   - the synthetic terminal event
   - the existing `run_complete` envelope with `final_status: "cancelled"`
6. clean up temporary input files
7. release the run from `ProcessManager`

### Persistence Consistency

`EventStore.delete_run()` must remain the single persistence deletion point.

It should:

- hold the existing lock across the whole delete operation
- delete the individual run JSON file
- rewrite `index.json` without the deleted run entry in the same critical section

This guarantees there is no state where the list entry exists but the file does not, or vice versa.

## Frontend Design

### Interrupt Control Placement

Place `Interrupt` in `SessionBar`.

Rationale:

- interrupt is a global control for the current live run, not a local card action
- `SessionBar` is the most stable and visible control area for run-level actions
- this avoids burying a destructive live control deep inside progress cards

Behavior:

- show only when:
  - `mode === "live"`
  - a `runId` exists
- clicking sets a local pending state
- pending state disables the button and changes the label to `Interrupting...`
- on success, the frontend waits for backend-driven lifecycle completion and transitions out of live mode when the terminal status arrives

### Delete Control Placement

Place `Delete` in each completed row of `RunList`.

Behavior:

- do not show for `run.status === "running"`
- show only for non-running items
- clicking opens a confirmation modal

### Delete Confirmation Modal

The modal must clearly state:

- deletion is permanent for this dashboard run record
- the corresponding backend run file will also be deleted

Actions:

- `Cancel`
- `Delete Permanently`

During request execution:

- disable destructive controls
- show pending state to prevent double submission

### Frontend Session Cleanup

If a deleted run is the currently opened replay run:

- clear the current session
- clear persisted session storage
- return the dashboard to idle

If a deleted run is not the current run:

- only remove it from the visible history list

### Frontend API Helpers

Add explicit helpers in `dashboard/frontend/src/utils/runApi.ts`:

- `cancelRun(runId)`
- `deleteRun(runId)`

They should normalize backend errors the same way existing run API helpers already do.

### Final Status Handling

The frontend must recognize `cancelled` as an ended state.

Implications:

- `useRunSession` should treat `cancelled` the same as other final statuses for leaving live mode
- `FinalSummaryCard` needs a user-facing explanation for `cancelled`
- failure analysis must not misclassify `cancelled` as a runtime crash or adversarial failure

## Expected File Touch Points

### Backend

- `dashboard/backend/server.py`
- `dashboard/backend/process_runner.py`
- `dashboard/backend/event_store.py`
- `dashboard/backend/models.py`

### Frontend

- `dashboard/frontend/src/App.tsx`
- `dashboard/frontend/src/components/SessionBar.tsx`
- `dashboard/frontend/src/components/RunList.tsx`
- `dashboard/frontend/src/hooks/useRunSession.ts`
- `dashboard/frontend/src/utils/runApi.ts`
- `dashboard/frontend/src/components/FinalSummaryCard.tsx`
- `dashboard/frontend/src/utils/failureAnalysis.ts`

### Tests

- backend run-control / persistence tests
- `RunList` tests
- `SessionBar` and/or `App` tests
- `useRunSession` tests
- `runApi` tests

## Testing Strategy

### Backend Tests

Add coverage for:

1. cancelling a running run:
   - subprocess termination path runs
   - final status becomes `cancelled`
   - synthetic terminal event is persisted
   - `index.json` gets a completed entry with `final_status: "cancelled"`
2. cancelling a completed run:
   - returns `409`
   - no persistence mutation
3. deleting a running run:
   - returns `409`
   - no file deletion
4. deleting a completed run:
   - deletes the run JSON file
   - removes the index entry
   - preserves consistency under the event-store lock

### Frontend Tests

Add coverage for:

1. `Interrupt` visibility and pending state for live runs
2. `Delete` visibility only for completed runs
3. confirmation modal open/cancel/confirm behavior
4. deleting the currently opened replay run clears session state
5. `cancelled` runs transition out of live mode correctly
6. run API helpers for cancel and delete error handling

### Manual Verification

Verify:

1. start a solve, click `Interrupt`, and confirm the run ends as `cancelled`
2. the interrupted run remains visible in history
3. a completed run shows `Delete`, but a running run does not
4. deleting a completed run removes it from the UI
5. the corresponding `dashboard/data/runs/<run_id>.json` file is removed
6. the corresponding entry disappears from `dashboard/data/runs/index.json`
7. deleting the currently opened replay run returns the UI to idle

## Risks

### 1. Half-deleted persisted state

Risk:

- list entry removed but file left behind, or file removed but list entry left behind

Mitigation:

- perform file deletion and `index.json` rewrite under the event-store lock

### 2. Live session stuck after interrupt

Risk:

- frontend remains in live mode because cancellation does not produce a recognizable final status

Mitigation:

- cancellation must emit a standard terminal event with `status: "cancelled"`
- frontend should use existing final-status completion logic rather than a special side channel

### 3. Misclassified cancelled runs

Risk:

- `cancelled` shows up as a generic failure or crash

Mitigation:

- explicitly add `cancelled` handling to summary and failure-analysis UI text

## Success Criteria

This feature is complete when all of the following are true:

1. a running dashboard solve can be interrupted from the UI
2. interrupted runs finish as `cancelled` and remain in history
3. completed runs can be deleted only after confirmation
4. deleting a completed run removes both the persisted run file and the `index.json` entry
5. deleting an opened replay run clears the active frontend session
6. active runs cannot be deleted and completed runs cannot be cancelled
7. focused backend and frontend tests protect the lifecycle and consistency rules
