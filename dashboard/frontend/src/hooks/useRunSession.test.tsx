import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useRunSession } from './useRunSession';

interface Deferred<T> {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T | PromiseLike<T>) => void;
}

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close(): void {
    this.emitClose();
  }

  emitClose(): void {
    this.onclose?.({ code: 1006, reason: '', wasClean: false } as CloseEvent);
  }

  open(): void {
    this.onopen?.({ type: 'open' } as Event);
  }

  static reset(): void {
    MockWebSocket.instances = [];
  }
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: Deferred<T>['resolve'];
  let reject!: Deferred<T>['reject'];
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return {
    promise,
    reject,
    resolve,
  };
}

function createResponse(payload: Record<string, unknown>): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

function createErrorResponse(status: number, payload: Record<string, unknown>): Response {
  return {
    ok: false,
    status,
    json: async () => payload,
  } as Response;
}

describe('useRunSession', () => {
  beforeEach(() => {
    window.localStorage.clear();
    MockWebSocket.reset();
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
    Object.defineProperty(window, 'WebSocket', {
      configurable: true,
      value: MockWebSocket as unknown as typeof WebSocket,
      writable: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('hydrates a running run from /api/runs/:id and marks it live', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        run_id: 'run-1',
        problem_id: 'p1',
        problem: { description: 'demo' },
        config: {},
        final_status: null,
        events: [
          { event: { type: 'solve_start', problem_id: 'p1' }, seq: 0, timestamp: 1 },
          { event: { type: 'phase_start', phase: 'testgen_phase' }, seq: 1, timestamp: 2 },
        ],
      }),
    } as Response);

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await act(async () => {
      await result.current.selectLiveRun('run-1');
    });

    await waitFor(() => expect(result.current.session.runId).toBe('run-1'));
    expect(result.current.session.mode).toBe('live');
    expect(result.current.session.events.map((event) => event.seq)).toEqual([0, 1]);
    expect(result.current.session.shouldConnectLive).toBe(true);

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
    });
    await waitFor(() => expect(result.current.session.wsStatus).toBe('connected'));

    expect(MockWebSocket.instances[0].url).toContain('/ws/live/run-1');
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'run-1',
      mode: 'live',
    });
  });

  it('restores the persisted run and falls back to replay when the run already finished', async () => {
    window.localStorage.setItem(
      'algopilot.dashboard.lastRun',
      JSON.stringify({
        runId: 'run-7',
        mode: 'live',
        selectedStageId: 'verify',
        selectedTimelineId: 'verify-1',
        replayCursor: 0,
        updatedAt: 1234,
      }),
    );

    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        run_id: 'run-7',
        problem_id: 'p7',
        problem: { description: 'finished' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'p7' }, seq: 0, timestamp: 1 },
          { event: { type: 'final', status: 'accepted' }, seq: 1, timestamp: 2 },
        ],
      }),
    } as Response);

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await waitFor(() => expect(result.current.session.runId).toBe('run-7'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(result.current.session.selectedStageId).toBe('verify');
    expect(result.current.session.selectedTimelineId).toBe('verify-1');
    expect(result.current.session.replayCursor).toBe(2);
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('selects a completed run in replay-ready mode with the cursor at the end', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        run_id: 'run-finished',
        problem_id: 'pf',
        problem: { description: 'finished' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'pf' }, seq: 0, timestamp: 1 },
          { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
          { event: { type: 'final', status: 'accepted' }, seq: 2, timestamp: 3 },
        ],
      }),
    } as Response);

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await act(async () => {
      await result.current.selectReplayRun('run-finished');
    });

    await waitFor(() => expect(result.current.session.runId).toBe('run-finished'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(result.current.session.replayCursor).toBe(3);
  });

  it('backfills and reconnects after the live websocket closes unexpectedly', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          run_id: 'run-2',
          problem_id: 'p2',
          problem: { description: 'demo' },
          config: {},
          final_status: null,
          events: [
            { event: { type: 'solve_start', problem_id: 'p2' }, seq: 0, timestamp: 1 },
            { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          run_id: 'run-2',
          problem_id: 'p2',
          problem: { description: 'demo' },
          config: {},
          final_status: null,
          events: [
            { event: { type: 'solve_start', problem_id: 'p2' }, seq: 0, timestamp: 1 },
            { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
            { event: { type: 'node_enter', node_id: 'generate_code', subgraph: 'codegen' }, seq: 2, timestamp: 3 },
          ],
        }),
      } as Response);

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await act(async () => {
      await result.current.selectLiveRun('run-2');
    });

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    act(() => {
      MockWebSocket.instances[0].open();
    });
    await waitFor(() => expect(result.current.session.wsStatus).toBe('connected'));

    act(() => {
      MockWebSocket.instances[0].emitClose();
    });

    expect(result.current.session.events.map((event) => event.seq)).toEqual([0, 1]);

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.session.wsStatus).toBe('reconnecting'));
    await waitFor(() => expect(result.current.session.events.map((event) => event.seq)).toEqual([0, 1, 2]));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(2));

    act(() => {
      MockWebSocket.instances[1].open();
    });
    await waitFor(() => expect(result.current.session.wsStatus).toBe('connected'));
  });

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

  it('ignores an in-flight hydrate result after dropRun clears the matching session', async () => {
    const pending = createDeferred<Response>();
    const fetchImpl = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs/run-delete') {
        return pending.promise;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    act(() => {
      void result.current.selectReplayRun('run-delete');
    });

    await waitFor(() => expect(result.current.session.hydrationStatus).toBe('restoring'));

    act(() => {
      result.current.dropRun('run-delete');
    });

    expect(result.current.session.runId).toBeNull();
    expect(window.localStorage.getItem('algopilot.dashboard.lastRun')).toBeNull();

    await act(async () => {
      pending.resolve(createResponse({
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
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBeNull());
    expect(result.current.session.mode).toBe('idle');
    expect(result.current.session.hydrationStatus).toBe('idle');
  });

  it('ignores a slower older hydration response after a newer run selection resolves first', async () => {
    const pendingRunA = createDeferred<Response>();
    const pendingRunB = createDeferred<Response>();
    const fetchImpl = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs/run-a') {
        return pendingRunA.promise;
      }
      if (url === '/api/runs/run-b') {
        return pendingRunB.promise;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    act(() => {
      void result.current.selectLiveRun('run-a');
      void result.current.selectReplayRun('run-b');
    });

    await act(async () => {
      pendingRunB.resolve(createResponse({
        run_id: 'run-b',
        problem_id: 'pb',
        problem: { description: 'replay' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'pb' }, seq: 0, timestamp: 1 },
          { event: { type: 'final', status: 'accepted' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('run-b'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(0);

    await act(async () => {
      pendingRunA.resolve(createResponse({
        run_id: 'run-a',
        problem_id: 'pa',
        problem: { description: 'live' },
        config: {},
        final_status: null,
        events: [
          { event: { type: 'solve_start', problem_id: 'pa' }, seq: 0, timestamp: 1 },
          { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('run-b'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(result.current.session.events.map((event) => event.seq)).toEqual([0, 1]);
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'run-b',
      mode: 'replay',
    });
  });

  it('ignores an in-flight persisted restore when a later explicit selection finishes first', async () => {
    window.localStorage.setItem(
      'algopilot.dashboard.lastRun',
      JSON.stringify({
        runId: 'restore-run',
        mode: 'live',
        selectedStageId: null,
        selectedTimelineId: null,
        replayCursor: 0,
        updatedAt: 1234,
      }),
    );

    const pendingRestore = createDeferred<Response>();
    const pendingUserSelection = createDeferred<Response>();
    const fetchImpl = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs/restore-run') {
        return pendingRestore.promise;
      }
      if (url === '/api/runs/user-run') {
        return pendingUserSelection.promise;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/runs/restore-run'));

    act(() => {
      void result.current.selectLiveRun('user-run');
    });

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/runs/user-run'));

    await act(async () => {
      pendingUserSelection.resolve(createResponse({
        run_id: 'user-run',
        problem_id: 'pu',
        problem: { description: 'picked by user' },
        config: {},
        final_status: null,
        events: [
          { event: { type: 'solve_start', problem_id: 'pu' }, seq: 0, timestamp: 1 },
          { event: { type: 'phase_start', phase: 'verify_phase' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('user-run'));
    expect(result.current.session.mode).toBe('live');
    expect(result.current.session.shouldConnectLive).toBe(true);
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));
    expect(MockWebSocket.instances[0].url).toContain('/ws/live/user-run');

    await act(async () => {
      pendingRestore.resolve(createResponse({
        run_id: 'restore-run',
        problem_id: 'pr',
        problem: { description: 'restored' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'pr' }, seq: 0, timestamp: 1 },
          { event: { type: 'final', status: 'accepted' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('user-run'));
    expect(result.current.session.mode).toBe('live');
    expect(result.current.session.shouldConnectLive).toBe(true);
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('/ws/live/user-run');
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'user-run',
      mode: 'live',
    });
  });

  it('ignores a stale failed persisted restore after a newer selection succeeds and preserves storage', async () => {
    window.localStorage.setItem(
      'algopilot.dashboard.lastRun',
      JSON.stringify({
        runId: 'restore-run',
        mode: 'live',
        selectedStageId: null,
        selectedTimelineId: null,
        replayCursor: 0,
        updatedAt: 1234,
      }),
    );

    const pendingRestore = createDeferred<Response>();
    const pendingUserSelection = createDeferred<Response>();
    const fetchImpl = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs/restore-run') {
        return pendingRestore.promise;
      }
      if (url === '/api/runs/user-run') {
        return pendingUserSelection.promise;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/runs/restore-run'));

    act(() => {
      void result.current.selectReplayRun('user-run');
    });

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/runs/user-run'));

    await act(async () => {
      pendingUserSelection.resolve(createResponse({
        run_id: 'user-run',
        problem_id: 'pu',
        problem: { description: 'picked by user' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'pu' }, seq: 0, timestamp: 1 },
          { event: { type: 'final', status: 'accepted' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('user-run'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'user-run',
      mode: 'replay',
    });

    await act(async () => {
      pendingRestore.resolve(createErrorResponse(404, { detail: 'Run not found' }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('user-run'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.hydrationStatus).toBe('ready');
    expect(window.localStorage.getItem('algopilot.dashboard.lastRun')).not.toBeNull();
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'user-run',
      mode: 'replay',
    });
  });

  it('ignores a stale reconnect hydration after a later explicit selection succeeds', async () => {
    const pendingReconnect = createDeferred<Response>();
    const pendingUserSelection = createDeferred<Response>();
    let liveRunFetchCount = 0;
    const fetchImpl = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs/live-run') {
        liveRunFetchCount += 1;
        if (liveRunFetchCount === 1) {
          return Promise.resolve(createResponse({
            run_id: 'live-run',
            problem_id: 'pl',
            problem: { description: 'live' },
            config: {},
            final_status: null,
            events: [
              { event: { type: 'solve_start', problem_id: 'pl' }, seq: 0, timestamp: 1 },
              { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
            ],
          }));
        }
        return pendingReconnect.promise;
      }
      if (url === '/api/runs/replay-run') {
        return pendingUserSelection.promise;
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });

    const { result } = renderHook(() => useRunSession({ fetchImpl, storage: window.localStorage }));

    await act(async () => {
      await result.current.selectLiveRun('live-run');
    });

    await waitFor(() => expect(result.current.session.runId).toBe('live-run'));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    act(() => {
      MockWebSocket.instances[0].open();
    });
    await waitFor(() => expect(result.current.session.wsStatus).toBe('connected'));

    act(() => {
      MockWebSocket.instances[0].emitClose();
    });

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.session.wsStatus).toBe('reconnecting'));

    act(() => {
      void result.current.selectReplayRun('replay-run');
    });

    await waitFor(() => expect(fetchImpl).toHaveBeenCalledWith('/api/runs/replay-run'));

    await act(async () => {
      pendingUserSelection.resolve(createResponse({
        run_id: 'replay-run',
        problem_id: 'pr',
        problem: { description: 'replay' },
        config: {},
        final_status: 'accepted',
        events: [
          { event: { type: 'solve_start', problem_id: 'pr' }, seq: 0, timestamp: 1 },
          { event: { type: 'final', status: 'accepted' }, seq: 1, timestamp: 2 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('replay-run'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(1);

    await act(async () => {
      pendingReconnect.resolve(createResponse({
        run_id: 'live-run',
        problem_id: 'pl',
        problem: { description: 'live' },
        config: {},
        final_status: null,
        events: [
          { event: { type: 'solve_start', problem_id: 'pl' }, seq: 0, timestamp: 1 },
          { event: { type: 'phase_start', phase: 'codegen_phase' }, seq: 1, timestamp: 2 },
          { event: { type: 'node_enter', node_id: 'generate_code', subgraph: 'codegen' }, seq: 2, timestamp: 3 },
        ],
      }));
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.session.runId).toBe('replay-run'));
    expect(result.current.session.mode).toBe('replay');
    expect(result.current.session.events.map((event) => event.seq)).toEqual([0, 1]);
    expect(result.current.session.shouldConnectLive).toBe(false);
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'replay-run',
      mode: 'replay',
    });
  });
});
