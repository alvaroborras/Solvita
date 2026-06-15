import { describe, expect, it } from 'vitest';

import { createInitialRunSessionState, reduceRunSession } from './runSessionReducer';

describe('reduceRunSession', () => {
  it('creates the idle session state', () => {
    expect(createInitialRunSessionState()).toEqual({
      runId: null,
      mode: 'idle',
      hydrationStatus: 'idle',
      wsStatus: 'disconnected',
      runDetail: null,
      events: [],
      shouldConnectLive: false,
      selectedStageId: null,
      selectedTimelineId: null,
      replayCursor: 0,
    });
  });

  it('hydrates a running run without losing selected stage state', () => {
    const initial = {
      ...createInitialRunSessionState(),
      selectedStageId: 'codegen',
    };

    const next = reduceRunSession(initial, {
      type: 'hydrate_succeeded',
      runDetail: {
        runId: 'run-1',
        problemId: 'p1',
        problem: {},
        config: {},
        finalStatus: null,
      },
      events: [
        { type: 'solve_start', seq: 0, ts: 1, problem_id: 'p1' },
        { type: 'phase_start', phase: 'codegen_phase', seq: 1, ts: 2 },
      ],
      mode: 'live',
      shouldConnectLive: true,
    });

    expect(next.runId).toBe('run-1');
    expect(next.mode).toBe('live');
    expect(next.hydrationStatus).toBe('ready');
    expect(next.runDetail?.problemId).toBe('p1');
    expect(next.events).toHaveLength(2);
    expect(next.shouldConnectLive).toBe(true);
    expect(next.selectedStageId).toBe('codegen');
  });
});
