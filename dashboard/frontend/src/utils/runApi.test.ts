import { describe, expect, it } from 'vitest';

import { cancelRun, createRun, deleteRun, fetchRunDetail } from './runApi';

describe('createRun', () => {
  it('returns the run id when the backend creates a run', async () => {
    const response = await createRun(
      { description: 'demo' },
      { max_iterations: 3 },
      async () => ({
        ok: true,
        json: async () => ({ run_id: 'abc123', ws_url: 'ws://example/ws/live/abc123' }),
      }) as Response
    );

    expect(response.runId).toBe('abc123');
    expect(response.raw.ws_url).toBe('ws://example/ws/live/abc123');
  });

  it('throws when the backend response does not include a run id', async () => {
    await expect(
      createRun(
        { description: 'demo' },
        { max_iterations: 3 },
        async () => ({
          ok: true,
          json: async () => ({ status: 'running' }),
        }) as Response
      )
    ).rejects.toThrow('missing run_id');
  });
});

describe('fetchRunDetail', () => {
  it('returns the run detail payload when the backend succeeds', async () => {
    const detail = await fetchRunDetail(
      'run-1',
      async () => ({
        ok: true,
        json: async () => ({
          run_id: 'run-1',
          problem_id: 'p1',
          final_status: null,
          events: [],
        }),
      }) as Response,
    );

    expect(detail.run_id).toBe('run-1');
    expect(detail.problem_id).toBe('p1');
  });

  it('throws on 404 so the session can drop an invalid persisted run', async () => {
    await expect(
      fetchRunDetail(
        'run-missing',
        async () => ({
          ok: false,
          status: 404,
          json: async () => ({ detail: 'Run not found' }),
        }) as Response,
      ),
    ).rejects.toThrow('Run not found');
  });

  it('throws when the payload is malformed even if the response is ok', async () => {
    await expect(
      fetchRunDetail(
        'run-bad',
        async () => ({
          ok: true,
          status: 200,
          json: async () => ({ error: 'Run not found' }),
        }) as Response,
      ),
    ).rejects.toThrow('Run not found');
  });
});

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

  it('throws the backend message when cancelRun fails', async () => {
    await expect(
      cancelRun(
        'run-live',
        async () => ({
          ok: false,
          status: 404,
          json: async () => ({ detail: 'Run not found' }),
        }) as Response,
      ),
    ).rejects.toThrow('Run not found');
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

  it('throws the backend message when deleteRun fails', async () => {
    await expect(
      deleteRun(
        'run-live',
        async () => ({
          ok: false,
          status: 409,
          json: async () => ({ detail: 'Cannot delete a running run' }),
        }) as Response,
      ),
    ).rejects.toThrow('Cannot delete a running run');
  });
});
