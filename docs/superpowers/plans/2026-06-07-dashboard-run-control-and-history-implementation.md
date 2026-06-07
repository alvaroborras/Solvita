# Dashboard Run Control And History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add interrupt control for live dashboard solves and confirmed deletion for completed run history while keeping backend persistence and frontend session state consistent.

**Architecture:** Keep interrupt and delete as two explicit backend flows: `POST /api/runs/{run_id}/cancel` for active processes and `DELETE /api/runs/{run_id}` for persisted completed runs. On the frontend, wire interrupt into `SessionBar`, keep delete inside `RunList` with a confirmation modal, and centralize “current run was deleted” cleanup in `useRunSession` so the UI cannot point at a removed record.

**Tech Stack:** FastAPI, asyncio subprocess management, Pydantic, pytest, React 18, TypeScript, Testing Library, Vitest

---

## File Map

- `dashboard/backend/process_runner.py`
  - Owns subprocess lifecycle, event buffering, terminal finalization, and temporary-file cleanup.
  - Will gain a real cancel finalization path guarded against double-finalization.
- `dashboard/backend/server.py`
  - Owns dashboard HTTP routes.
  - Will gain the cancel endpoint and stricter delete semantics.
- `dashboard/backend/models.py`
  - Owns typed API response models.
  - Will gain explicit cancel/delete response types.
- `dashboard/backend/event_store.py`
  - Owns persisted run JSON and `index.json` maintenance.
  - Delete semantics stay here and remain the single persistence delete point.
- `tests/dashboard/test_run_lifecycle.py`
  - Owns backend lifecycle regression coverage.
  - Will gain cancel and delete consistency tests.
- `dashboard/frontend/src/utils/runApi.ts`
  - Owns run HTTP helpers.
  - Will gain `cancelRun` and `deleteRun`.
- `dashboard/frontend/src/utils/runApi.test.ts`
  - Owns run API helper tests.
- `dashboard/frontend/src/hooks/useRunSession.ts`
  - Owns live/replay session hydration and current-run cleanup.
  - Will gain a run-drop helper for deleted records.
- `dashboard/frontend/src/hooks/useRunSession.test.tsx`
  - Owns session lifecycle tests.
- `dashboard/frontend/src/components/SessionBar.tsx`
  - Owns top-level live-run controls.
  - Will gain the interrupt button props and UI.
- `dashboard/frontend/src/styles/journey.css`
  - Owns shared dashboard component styling.
  - Will gain the interrupt danger-button treatment used by `SessionBar`.
- `dashboard/frontend/src/components/SessionBar.test.tsx`
  - Owns session bar interaction tests.
- `dashboard/frontend/src/components/RunList.tsx`
  - Owns run polling, list rendering, and per-run actions.
  - Will gain completed-run delete controls plus the confirmation modal.
- `dashboard/frontend/src/components/RunList.test.tsx`
  - Owns run-list action tests.
- `dashboard/frontend/src/components/FinalSummaryCard.tsx`
  - Owns ended-run summary copy.
  - Will gain `cancelled` copy.
- `dashboard/frontend/src/utils/failureAnalysis.ts`
  - Owns failure analysis generation.
  - Will explicitly ignore `cancelled` as a failure mode.
- `dashboard/frontend/src/utils/failureAnalysis.test.ts`
  - Owns failure-analysis regression coverage.
- `dashboard/frontend/src/App.tsx`
  - Owns top-level wiring between session state, controls, and run history callbacks.
- `dashboard/frontend/src/App.test.tsx`
  - Owns end-to-end dashboard interaction coverage.

## Execution Note

The dashboard frontend tree currently exists in the working tree and has untracked files that are not present in the isolated worktree created earlier. Implement the plan in the main workspace at:

`/ssd-disk/lih/Software-Engineering-work/algorithm-agent`

Do not revert unrelated edits.

### Task 1: Backend cancel finalizes runs as `cancelled`

**Files:**
- Modify: `dashboard/backend/models.py`
- Modify: `dashboard/backend/process_runner.py`
- Modify: `dashboard/backend/server.py`
- Test: `tests/dashboard/test_run_lifecycle.py`

- [ ] **Step 1: Write the failing backend cancel tests**

Add these helpers and tests to `tests/dashboard/test_run_lifecycle.py`:

```python
import pytest
from fastapi import HTTPException
```

```python
class _FakeCancellableProcess:
    def __init__(self, chunks: list[bytes]) -> None:
        self.stdout = _FakeStdout(chunks)
        self.returncode = None
        self.terminated = False

    async def wait(self) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
```

```python
def test_cancel_run_persists_cancelled_final_event(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Demo"}}, config={})
    proc.problem_id = "demo-problem"
    proc._process = _FakeCancellableProcess([])
    proc._tmp_file = tmp_path / "cancel-input.json"
    proc._tmp_file.write_text("{}", encoding="utf-8")
    proc._ws_manager = _BroadcastCollector()
    proc._event_store = server.event_store

    result = asyncio.run(server.cancel_run(proc.run_id))

    assert result.run_id == proc.run_id
    assert result.cancelled is True
    assert result.final_status == "cancelled"
    assert proc._process.terminated is True

    stored = server.event_store.get_run(proc.run_id)
    assert stored is not None
    assert stored["final_status"] == "cancelled"
    assert stored["events"][-1]["event"]["type"] == "final"
    assert stored["events"][-1]["event"]["status"] == "cancelled"
    assert any(
        message["event"]["type"] == "run_complete" and message["event"]["final_status"] == "cancelled"
        for _, message in proc._ws_manager.messages
    )
    assert server.process_manager.get(proc.run_id) is None
    assert proc._tmp_file.exists() is False
```

```python
def test_cancel_run_rejects_non_running_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Done"}}, config={})
    proc.status = "completed"
    proc.final_status = "success"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.cancel_run(proc.run_id))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Run is not active"
```

- [ ] **Step 2: Run the backend cancel tests to verify they fail**

Run: `pytest tests/dashboard/test_run_lifecycle.py -q`

Expected:
- `AttributeError` / route-missing failure for `server.cancel_run`
- or assertion failures because cancel does not yet persist a final `cancelled` event

- [ ] **Step 3: Add explicit cancel response models**

Update `dashboard/backend/models.py` with:

```python
class RunCancelResponse(BaseModel):
    run_id: str
    cancelled: bool
    final_status: str


class RunDeleteResponse(BaseModel):
    run_id: str
    deleted: bool
```

- [ ] **Step 4: Implement one-time finalization and persisted cancel flow**

Update `dashboard/backend/process_runner.py`:

```python
        self._ws_manager: WebSocketManager | None = None
        self._event_store: EventStore | None = None
        self._finalized = False
        self._finalize_lock = asyncio.Lock()
```

Inside `start(...)`:

```python
        self._ws_manager = ws_manager
        self._event_store = event_store
```

Add these helpers:

```python
    async def _finalize_once(self, final_status: str | None) -> bool:
        async with self._finalize_lock:
            if self._finalized:
                return False
            self._finalized = True

            self.final_status = final_status
            self.status = "completed"
            self.completed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            if self._event_store is not None:
                self._event_store.save_run(
                    run_id=self.run_id,
                    problem_id=self.problem_id,
                    problem=self.problem,
                    config=self.config,
                    events=self.events,
                    started_at=self.started_at,
                    final_status=final_status,
                    completed_at=self.completed_at,
                )

            if self._ws_manager is not None:
                await self._ws_manager.broadcast(self.run_id, {
                    "seq": self._seq,
                    "timestamp": time.time(),
                    "event": {"type": "run_complete", "final_status": final_status},
                })

            if self._tmp_file and self._tmp_file.exists():
                self._tmp_file.unlink()
            if self._manager is not None:
                self._manager.release(self.run_id)
            return True
```

```python
    def _append_terminal_event(self, status: str) -> None:
        wrapped = {
            "seq": self._seq,
            "timestamp": time.time(),
            "event": {"type": "final", "status": status},
        }
        self._seq += 1
        self.events.append(wrapped)
```
Update the tail of `_read_stream(...)`:

```python
        final_status = None
        for e in reversed(self.events):
            ev = e.get("event", e)
            if ev.get("type") == "final":
                final_status = ev.get("status")
                break

        await self._finalize_once(final_status)
```

Replace `cancel()` with:

```python
    async def cancel(self) -> str:
        if self.status != "running":
            raise RuntimeError("Run is not active")

        if self._process and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()

        has_final = any(
            (entry.get("event", entry)).get("type") == "final"
            for entry in self.events
        )
        if not has_final:
            self._append_terminal_event("cancelled")
            if self._ws_manager is not None:
                await self._ws_manager.broadcast(self.run_id, self.events[-1])

        await self._finalize_once("cancelled")
        return "cancelled"
```

- [ ] **Step 5: Add the cancel route**

Update `dashboard/backend/server.py` imports:

```python
        RunCancelResponse,
        RunDeleteResponse,
```

Add the new route:

```python
@app.post("/api/runs/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(run_id: str):
    proc = process_manager.get(run_id)
    if proc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if proc.status != "running":
        raise HTTPException(status_code=409, detail="Run is not active")

    final_status = await proc.cancel()
    return RunCancelResponse(
        run_id=run_id,
        cancelled=True,
        final_status=final_status,
    )
```

- [ ] **Step 6: Run the backend cancel tests to verify they pass**

Run: `pytest tests/dashboard/test_run_lifecycle.py -q`

Expected:
- the new cancel tests pass
- existing run lifecycle tests still pass

- [ ] **Step 7: Commit**

```bash
git add dashboard/backend/models.py dashboard/backend/process_runner.py dashboard/backend/server.py tests/dashboard/test_run_lifecycle.py
git commit -m "feat: persist cancelled dashboard runs"
```

### Task 2: Backend delete rejects active runs and keeps persisted state consistent

**Files:**
- Modify: `dashboard/backend/server.py`
- Modify: `dashboard/backend/models.py`
- Test: `tests/dashboard/test_run_lifecycle.py`

- [ ] **Step 1: Write the failing delete tests**

Append these tests to `tests/dashboard/test_run_lifecycle.py`:

```python
def test_delete_run_rejects_active_process(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    proc = server.process_manager.create_run(problem={"_metadata": {"name": "Live"}}, config={})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.delete_run(proc.run_id))

    assert exc.value.status_code == 409
    assert exc.value.detail == "Cannot delete a running run"
```

```python
def test_delete_run_removes_file_and_index_entry(monkeypatch, tmp_path):
    _configure_dashboard_runtime(monkeypatch, tmp_path)

    run_id = "done-run"
    server.event_store.save_run(
        run_id=run_id,
        problem_id="demo-problem",
        problem={"_metadata": {"name": "Demo"}},
        config={},
        events=[
            {"seq": 0, "timestamp": 1.0, "event": {"type": "solve_start", "problem_id": "demo-problem"}},
            {"seq": 1, "timestamp": 2.0, "event": {"type": "final", "status": "success", "iterations": 1, "pass_rate": 1.0}},
        ],
        started_at="2026-06-07T00:00:00Z",
        final_status="success",
        completed_at="2026-06-07T00:00:02Z",
    )

    result = asyncio.run(server.delete_run(run_id))

    assert result.run_id == run_id
    assert result.deleted is True
    assert server.event_store.get_run(run_id) is None
    assert all(entry["run_id"] != run_id for entry in server.event_store.list_runs())
```

- [ ] **Step 2: Run the delete tests to verify they fail**

Run: `pytest tests/dashboard/test_run_lifecycle.py -q`

Expected:
- active-delete test fails because the route currently deletes without checking `ProcessManager`
- persisted-delete test fails because the route returns a raw dict / missing `run_id`

- [ ] **Step 3: Tighten the delete route**

Update `dashboard/backend/server.py`:

```python
@app.delete("/api/runs/{run_id}", response_model=RunDeleteResponse)
async def delete_run(run_id: str):
    proc = process_manager.get(run_id)
    if proc is not None and proc.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running run")

    deleted = event_store.delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")

    return RunDeleteResponse(
        run_id=run_id,
        deleted=True,
    )
```

- [ ] **Step 4: Run the backend lifecycle tests to verify they pass**

Run: `pytest tests/dashboard/test_run_lifecycle.py -q`

Expected:
- both delete tests pass
- cancel tests remain green

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/server.py tests/dashboard/test_run_lifecycle.py
git commit -m "feat: protect dashboard run deletion semantics"
```

### Task 3: Frontend API helpers and session cleanup for cancelled or deleted runs

**Files:**
- Modify: `dashboard/frontend/src/utils/runApi.ts`
- Modify: `dashboard/frontend/src/utils/runApi.test.ts`
- Modify: `dashboard/frontend/src/hooks/useRunSession.ts`
- Modify: `dashboard/frontend/src/hooks/useRunSession.test.tsx`

- [ ] **Step 1: Write the failing frontend API and session tests**

Add to `dashboard/frontend/src/utils/runApi.test.ts`:

```ts
import { cancelRun, createRun, deleteRun, fetchRunDetail } from './runApi';
```

```ts
describe('cancelRun', () => {
  it('returns the backend cancel payload', async () => {
    const payload = await cancelRun(
      'run-live',
      async () => ({
        ok: true,
        status: 200,
        json: async () => ({ run_id: 'run-live', cancelled: true, final_status: 'cancelled' }),
      }) as Response,
    );

    expect(payload.run_id).toBe('run-live');
    expect(payload.final_status).toBe('cancelled');
  });
});

describe('deleteRun', () => {
  it('returns the backend delete payload', async () => {
    const payload = await deleteRun(
      'run-done',
      async () => ({
        ok: true,
        status: 200,
        json: async () => ({ run_id: 'run-done', deleted: true }),
      }) as Response,
    );

    expect(payload.run_id).toBe('run-done');
    expect(payload.deleted).toBe(true);
  });
});
```

Add to `dashboard/frontend/src/hooks/useRunSession.test.tsx`:

```ts
it('switches a live run to replay when a cancelled final event arrives', async () => {
  const fetchImpl = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      run_id: 'run-cancel',
      problem_id: 'p1',
      problem: { description: 'demo' },
      config: {},
      final_status: null,
      events: [{ event: { type: 'solve_start', problem_id: 'p1' }, seq: 0, timestamp: 1 }],
    }),
  } as Response);

  const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

  await act(async () => {
    await result.current.selectLiveRun('run-cancel');
  });

  await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
  act(() => {
    MockWebSocket.instances[0].open();
    MockWebSocket.instances[0].onmessage?.({
      data: JSON.stringify({
        type: 'final',
        status: 'cancelled',
        seq: 1,
        ts: 2,
      }),
    } as MessageEvent<string>);
  });

  await waitFor(() => expect(result.current.session.mode).toBe('replay'));
  expect(result.current.session.runDetail?.finalStatus).toBe('cancelled');
  expect(result.current.session.shouldConnectLive).toBe(false);
});
```

```ts
it('clears the current session when the active replay run is deleted', async () => {
  const fetchImpl = vi.fn().mockResolvedValue(createResponse({
    run_id: 'run-delete',
    problem_id: 'p1',
    problem: { description: 'demo' },
    config: {},
    final_status: 'success',
    events: [
      { event: { type: 'solve_start', problem_id: 'p1' }, seq: 0, timestamp: 1 },
      { event: { type: 'final', status: 'success' }, seq: 1, timestamp: 2 },
    ],
  }));

  const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

  await act(async () => {
    await result.current.selectReplayRun('run-delete');
  });
  await waitFor(() => expect(result.current.session.runId).toBe('run-delete'));

  act(() => {
    result.current.dropRun('run-delete');
  });

  expect(result.current.session.runId).toBeNull();
  expect(window.localStorage.getItem('algopilot.dashboard.lastRun')).toBeNull();
});
```

- [ ] **Step 2: Run the frontend API/session tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/utils/runApi.test.ts src/hooks/useRunSession.test.tsx`

Expected:
- missing export failures for `cancelRun`, `deleteRun`, or `dropRun`
- or assertion failures because cancelled/deleted flows are not implemented

- [ ] **Step 3: Implement API helpers and run-drop session cleanup**

Update `dashboard/frontend/src/utils/runApi.ts`:

```ts
export async function cancelRun(
  runId: string,
  fetchImpl: FetchLike = fetch,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(`/api/runs/${runId}/cancel`, { method: 'POST' });
  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Failed to interrupt run'));
  }
  return data;
}

export async function deleteRun(
  runId: string,
  fetchImpl: FetchLike = fetch,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(`/api/runs/${runId}`, { method: 'DELETE' });
  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Failed to delete run'));
  }
  return data;
}
```

Update `dashboard/frontend/src/hooks/useRunSession.ts`:

```ts
  const dropRun = useCallback((runId: string) => {
    const current = sessionRef.current;
    if (current.runId !== runId) {
      return;
    }
    clearPersistedRunSession(storage);
    setSocketEnabled(false);
    setSessionState(createInitialRunSessionState());
  }, [setSessionState, setSocketEnabled, storage]);
```

Return it:

```ts
    dropRun,
```

- [ ] **Step 4: Run the frontend API/session tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/utils/runApi.test.ts src/hooks/useRunSession.test.tsx`

Expected:
- the new API helper tests pass
- the new cancelled/deleted session tests pass
- existing session tests remain green

- [ ] **Step 5: Commit**

```bash
git add dashboard/frontend/src/utils/runApi.ts dashboard/frontend/src/utils/runApi.test.ts dashboard/frontend/src/hooks/useRunSession.ts dashboard/frontend/src/hooks/useRunSession.test.tsx
git commit -m "feat: add dashboard run api controls"
```

### Task 4: Add the interrupt button and completed-run delete modal UI

**Files:**
- Modify: `dashboard/frontend/src/components/SessionBar.tsx`
- Modify: `dashboard/frontend/src/styles/journey.css`
- Modify: `dashboard/frontend/src/components/SessionBar.test.tsx`
- Modify: `dashboard/frontend/src/components/RunList.tsx`
- Modify: `dashboard/frontend/src/components/RunList.test.tsx`
- Modify: `dashboard/frontend/src/App.tsx`

- [ ] **Step 1: Write the failing UI tests**

Update `dashboard/frontend/src/components/SessionBar.test.tsx`:

```ts
  it('shows and wires an interrupt action for live runs', async () => {
    const user = userEvent.setup();
    const onInterrupt = vi.fn();

    render(
      <SessionBar
        problemName="pair sum"
        runId="run-live"
        mode="live"
        wsStatus="connected"
        hydrationStatus="ready"
        canInterrupt
        interruptPending={false}
        onInterrupt={onInterrupt}
        onReconnect={vi.fn()}
        onResumeLatest={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /interrupt/i }));
    expect(onInterrupt).toHaveBeenCalledTimes(1);
  });
```

Update `dashboard/frontend/src/components/RunList.test.tsx`:

```ts
  it('shows delete for completed runs and removes the row after confirmed deletion', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            {
              run_id: 'done-1',
              problem_name: 'Done Run',
              problem_id: 'done-run',
              started_at: '2026-06-05T15:00:00Z',
              status: 'completed',
              final_status: 'success',
              iterations: 3,
              pass_rate: 1,
            },
          ],
        }));
      }
      if (url === '/api/runs/done-1' && init?.method === 'DELETE') {
        return Promise.resolve(createResponse({ run_id: 'done-1', deleted: true }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onDeletedRun = vi.fn();
    render(
      <RunList
        activeRunId={null}
        mode="idle"
        onSelectLive={vi.fn()}
        onSelectReplay={vi.fn()}
        onDeletedRun={onDeletedRun}
      />,
    );

    await user.click(await screen.findByRole('button', { name: /delete/i }));
    expect(screen.getByText(/permanently delete/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /delete permanently/i }));

    await waitFor(() => expect(screen.queryByText(/done run/i)).not.toBeInTheDocument());
    expect(onDeletedRun).toHaveBeenCalledWith('done-1');
  });
```

- [ ] **Step 2: Run the UI tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/components/SessionBar.test.tsx src/components/RunList.test.tsx`

Expected:
- prop/type failures for new interrupt/delete props
- or missing button/modal assertions

- [ ] **Step 3: Implement SessionBar interrupt props and App wiring**

Update the `SessionBarProps` interface in `dashboard/frontend/src/components/SessionBar.tsx`:

```ts
  canInterrupt?: boolean;
  interruptPending?: boolean;
  onInterrupt?: () => void;
```

Add the button in `.session-bar__actions`:

```tsx
        {canInterrupt && (
          <button
            type="button"
            className="session-bar__button session-bar__button--danger"
            disabled={interruptPending}
            onClick={onInterrupt}
          >
            {interruptPending ? 'Interrupting...' : 'Interrupt'}
          </button>
        )}
```

Update `dashboard/frontend/src/App.tsx`:

```ts
import { cancelRun } from './utils/runApi';
```

```ts
  const [interruptPending, setInterruptPending] = useState(false);
```

Update the `useRunSession` destructuring:

```ts
    dropRun,
```

```ts
  useEffect(() => {
    if (session.mode !== 'live') {
      setInterruptPending(false);
    }
  }, [session.mode, session.runId]);
```

```ts
  const handleInterruptRun = useCallback(async () => {
    if (!session.runId || session.mode !== 'live' || interruptPending) {
      return;
    }
    setInterruptPending(true);
    try {
      await cancelRun(session.runId);
    } catch {
      setInterruptPending(false);
    }
  }, [interruptPending, session.mode, session.runId]);
```

Pass the props:

```tsx
        canInterrupt={session.mode === 'live' && session.runId !== null}
        interruptPending={interruptPending}
        onInterrupt={() => {
          void handleInterruptRun();
        }}
```

Add the danger-button styling to `dashboard/frontend/src/styles/journey.css`:

```css
.session-bar__button--danger {
  background: rgba(247, 93, 93, 0.14);
  border-color: rgba(247, 93, 93, 0.22);
  color: var(--color-accent-red);
}

.session-bar__button--danger:hover:not(:disabled) {
  border-color: rgba(247, 93, 93, 0.34);
}
```

- [ ] **Step 4: Implement RunList delete controls and confirmation modal**

Update `RunListProps` in `dashboard/frontend/src/components/RunList.tsx`:

```ts
  onDeletedRun?: (runId: string) => void;
```

Add imports/state:

```ts
import { deleteRun } from '../utils/runApi';
```

```ts
  const [deleteTarget, setDeleteTarget] = useState<RunSummary | null>(null);
  const [deletePending, setDeletePending] = useState(false);
```

Add the per-row button for completed runs:

```tsx
              {run.status !== 'running' && (
                <button
                  type="button"
                  className="run-list__btn run-list__btn--danger"
                  onClick={() => setDeleteTarget(run)}
                >
                  Delete
                </button>
              )}
```

Add the confirm handler:

```ts
  const confirmDelete = async () => {
    if (!deleteTarget || deletePending) return;
    setDeletePending(true);
    try {
      await deleteRun(deleteTarget.run_id);
      setRuns((current) => current.filter((run) => run.run_id !== deleteTarget.run_id));
      onDeletedRun?.(deleteTarget.run_id);
      setDeleteTarget(null);
    } finally {
      setDeletePending(false);
    }
  };
```

Add the modal near the bottom of the component:

```tsx
      {deleteTarget && (
        <div className="run-list__modalBackdrop" role="presentation">
          <div className="run-list__modal surface-card" role="dialog" aria-modal="true" aria-labelledby="run-delete-title">
            <h3 id="run-delete-title">Delete this run record?</h3>
            <p>
              This permanently deletes the dashboard record for <strong>{deleteTarget.problem_name || deleteTarget.run_id}</strong>
              {' '}and removes the corresponding backend run file.
            </p>
            <div className="run-list__modalActions">
              <button type="button" className="run-list__btn" disabled={deletePending} onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button type="button" className="run-list__btn run-list__btn--danger" disabled={deletePending} onClick={() => { void confirmDelete(); }}>
                {deletePending ? 'Deleting...' : 'Delete Permanently'}
              </button>
            </div>
          </div>
        </div>
      )}
```

Add the matching style rules inside the existing `<style>` block in `dashboard/frontend/src/components/RunList.tsx`:

```css
        .run-list__btn--danger {
          background: rgba(247, 93, 93, 0.14);
          color: var(--color-accent-red);
        }
        .run-list__modalBackdrop {
          position: fixed;
          inset: 0;
          background: rgba(7, 16, 25, 0.68);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
          z-index: 30;
        }
        .run-list__modal {
          width: min(100%, 440px);
          display: grid;
          gap: 14px;
          padding: 20px;
        }
        .run-list__modalActions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
        }
```

Update `dashboard/frontend/src/App.tsx` to react to deletion:

```ts
  const handleDeletedRun = useCallback((runId: string) => {
    dropRun(runId);
  }, [dropRun]);
```

Pass it into `RunList`:

```tsx
          onDeletedRun={handleDeletedRun}
```

- [ ] **Step 5: Run the UI tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/components/SessionBar.test.tsx src/components/RunList.test.tsx`

Expected:
- interrupt button test passes
- delete confirm/remove-row test passes

- [ ] **Step 6: Commit**

```bash
git add dashboard/frontend/src/components/SessionBar.tsx dashboard/frontend/src/styles/journey.css dashboard/frontend/src/components/SessionBar.test.tsx dashboard/frontend/src/components/RunList.tsx dashboard/frontend/src/components/RunList.test.tsx dashboard/frontend/src/App.tsx
git commit -m "feat: add dashboard run controls"
```

### Task 5: Teach the UI what `cancelled` means and verify end-to-end behavior

**Files:**
- Modify: `dashboard/frontend/src/components/FinalSummaryCard.tsx`
- Modify: `dashboard/frontend/src/utils/failureAnalysis.ts`
- Modify: `dashboard/frontend/src/utils/failureAnalysis.test.ts`
- Modify: `dashboard/frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing copy and integration tests**

Add to `dashboard/frontend/src/utils/failureAnalysis.test.ts`:

```ts
  it('returns null for cancelled runs', () => {
    const analysis = buildFailureAnalysis({
      finalStatus: 'cancelled',
      artifact: createArtifact(),
      timeline: [],
      events: [],
    });

    expect(analysis).toBeNull();
  });
```

Extend `dashboard/frontend/src/App.test.tsx` with a cancel/delete integration test:

```ts
  it('interrupts a live run into cancelled replay and clears the session when that replay is deleted', async () => {
    const user = userEvent.setup();
    let runState: 'running' | 'cancelled' | 'deleted' = 'running';

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [{ id: 'p1', name: 'Pair Sum', source: 'showcase', preview: 'Find pair', difficulty: 'easy', is_showcase: true }],
        }));
      }
      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Find pair',
          public_tests: [],
          _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
        }));
      }
      if (url === '/api/runs' && init?.method === 'POST') {
        return Promise.resolve(createResponse({ run_id: 'run-live', status: 'running' }));
      }
      if (url === '/api/runs/run-live/cancel' && init?.method === 'POST') {
        runState = 'cancelled';
        return Promise.resolve(createResponse({ run_id: 'run-live', cancelled: true, final_status: 'cancelled' }));
      }
      if (url === '/api/runs/run-live' && init?.method === 'DELETE') {
        runState = 'deleted';
        return Promise.resolve(createResponse({ run_id: 'run-live', deleted: true }));
      }
      if (url === '/api/runs') {
        return Promise.resolve(createResponse({
          runs: runState === 'running'
            ? [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'running', final_status: null, iterations: null, pass_rate: null }]
            : runState === 'cancelled'
              ? [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'completed', final_status: 'cancelled', iterations: 1, pass_rate: 0 }]
              : [],
        }));
      }
      if (url === '/api/runs/run-live') {
        if (runState === 'deleted') {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ detail: 'Run not found' }),
          } as Response);
        }
        return Promise.resolve(createResponse({
          run_id: 'run-live',
          problem_id: 'p1',
          problem: { description: 'Find pair', _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true } },
          config: { max_iterations: 5 },
          final_status: runState === 'cancelled' ? 'cancelled' : null,
          events: runState === 'cancelled'
            ? [
                { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                { event: { type: 'final', status: 'cancelled' }, seq: 1, timestamp: 2 },
              ]
            : [
                { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
              ],
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await user.click(screen.getByRole('button', { name: /start solve/i }));
    await user.click((await screen.findAllByRole('button', { name: /^start solve$/i })).at(-1)!);
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    act(() => {
      MockWebSocket.instances[0].open();
    });

    await user.click(await screen.findByRole('button', { name: /interrupt/i }));

    act(() => {
      MockWebSocket.instances[0].emitMessage({ type: 'final', status: 'cancelled' });
    });

    await waitFor(() => expect(screen.getAllByText(/replay/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/The run was interrupted by the user/i)).toBeInTheDocument();

    await user.click(await screen.findByRole('button', { name: /delete/i }));
    await user.click(screen.getByRole('button', { name: /delete permanently/i }));

    await waitFor(() => expect(screen.getByText(/No active run/i)).toBeInTheDocument());
  });
```

- [ ] **Step 2: Run the copy/integration tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/utils/failureAnalysis.test.ts src/App.test.tsx`

Expected:
- cancelled-run failure analysis test fails because `cancelled` is currently treated as failure-ish
- App integration test fails because interrupt/delete controls and copy are not fully wired yet

- [ ] **Step 3: Implement cancelled summary and analysis behavior**

Update `dashboard/frontend/src/components/FinalSummaryCard.tsx`:

```ts
  if (finalStatus === 'cancelled') {
    return 'The run was interrupted by the user before the solver reached a final accepted answer.';
  }
```

Update `dashboard/frontend/src/utils/failureAnalysis.ts` near the top:

```ts
  if (finalStatus === 'success' || finalStatus === 'cancelled') {
    return null;
  }
```

- [ ] **Step 4: Run the focused integration tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/utils/failureAnalysis.test.ts src/App.test.tsx`

Expected:
- cancelled copy/analysis behavior passes
- interrupt → cancelled replay → confirmed delete → idle flow passes

- [ ] **Step 5: Run the full verification set**

Run: `pytest tests/dashboard/test_run_lifecycle.py -q && cd dashboard/frontend && npx vitest run src/utils/runApi.test.ts src/hooks/useRunSession.test.tsx src/components/SessionBar.test.tsx src/components/RunList.test.tsx src/utils/failureAnalysis.test.ts src/App.test.tsx && npm run build`

Expected:
- backend lifecycle tests: PASS
- frontend targeted tests: PASS
- production build: PASS

- [ ] **Step 6: Commit**

```bash
git add dashboard/frontend/src/components/FinalSummaryCard.tsx dashboard/frontend/src/utils/failureAnalysis.ts dashboard/frontend/src/utils/failureAnalysis.test.ts dashboard/frontend/src/App.test.tsx
git commit -m "feat: finish dashboard run history controls"
```
