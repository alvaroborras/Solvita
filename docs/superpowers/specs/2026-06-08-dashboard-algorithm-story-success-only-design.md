# Dashboard Algorithm Story Success-Only Design

Date: 2026-06-08
Topic: Hide algorithm-story playback unless the run ends in `success`

## Goal

Prevent the dashboard from showing algorithm-story playback for failed runs.

The playback should remain visible:

- while a run is still in progress
- after a run finishes with final status `success`

The playback should be hidden once a run has finished with any non-success final status.

## Current Problem

The dashboard currently renders `AlgorithmStoryCard` whenever an `algorithmVisualization` artifact exists, even if the solve ultimately failed.

This creates a misleading UI state:

- the page shows a polished step-by-step teaching playback
- but the actual run result says the solution was not accepted

## Scope

### In Scope

- frontend-only visibility rules for `AlgorithmStoryCard`
- final-status gating in the dashboard page
- regression tests for the visibility rule

### Out of Scope

- changing how algorithm-story artifacts are generated
- changing backend event payloads
- changing artifact extraction or storage
- changing live in-progress playback behavior
- changing the playback component’s internal UI

## Recommended Approach

Gate `AlgorithmStoryCard` rendering in `App.tsx` based on `finalStatus`.

Render rules:

- `finalStatus === null`
  - show the card if an algorithm-story artifact exists
- `finalStatus === "success"`
  - show the card
- `finalStatus !== null && finalStatus !== "success"`
  - do not render the card

This approach is preferable because:

- it keeps business-result gating in the page-level orchestration layer
- it avoids mixing presentation policy into artifact extraction
- it avoids adding result semantics to `AlgorithmStoryCard` itself

## UI Behavior

### Live Runs

For runs still in progress, the algorithm story may continue to appear as it does today.

Rationale:

- the user explicitly asked to hide playback when the final result is not success
- a run with no final verdict yet is not a failure yet

### Completed Successful Runs

If `finalStatus === "success"`, the algorithm-story playback remains visible.

### Completed Non-Success Runs

If `finalStatus` is any completed non-success value, the algorithm-story section must be absent.

This includes at least:

- `cancelled`
- `max_iterations`
- `terminal_failure`

and any other future terminal status that is not `success`.

## Expected File Touch Points

- `dashboard/frontend/src/App.tsx`
- `dashboard/frontend/src/App.test.tsx`

No backend changes are required.

## Testing Strategy

### Automated

Add or update an `App`-level regression test that proves:

1. a successful run can still show the algorithm-story card
2. a completed non-success run does not show the algorithm-story card

The most important contract is the second one.

### Manual

Verify in the browser that:

1. live/in-progress runs still show playback when available
2. successful completed runs still show playback
3. failed completed runs no longer show playback

## Risks

### Hiding Too Aggressively

If the visibility rule were implemented inside artifact extraction instead of render gating, other consumers could lose access to useful data.

Mitigation:

- keep the artifact intact
- only suppress the card at render time

### Coupling Final Status Into The Playback Component

If `AlgorithmStoryCard` itself were given result semantics, it would become harder to reuse and reason about.

Mitigation:

- keep the rule in `App.tsx`

## Success Criteria

This change is complete when:

1. failed runs no longer render `AlgorithmStoryCard`
2. successful runs still render it
3. live runs remain unchanged
4. the visibility rule is protected by an `App`-level regression test
