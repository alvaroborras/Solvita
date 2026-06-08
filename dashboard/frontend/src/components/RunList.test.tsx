import { act } from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import RunList from './RunList';

function createResponse(payload: Record<string, unknown>): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('RunList', () => {
  it('keeps the selected run in replay mode when the poll still reports it as running', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs') {
        return Promise.resolve(createResponse({
          runs: [
            {
              run_id: 'run-1',
              problem_name: 'Demo Run',
              problem_id: 'demo-run',
              started_at: '2026-06-05T15:00:00Z',
              status: 'running',
              final_status: null,
              iterations: 3,
              pass_rate: 0.5,
            },
          ],
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSelectLive = vi.fn();
    const onSelectReplay = vi.fn();

    render(
      <RunList
        activeRunId="run-1"
        mode="replay"
        onSelectLive={onSelectLive}
        onSelectReplay={onSelectReplay}
      />,
    );

    const openedButton = await screen.findByRole('button', { name: /opened/i });
    expect(openedButton).toBeDisabled();
    expect(openedButton.closest('article')).toHaveClass('run-list__item--selected');
    expect(openedButton.closest('article')).toHaveClass('run-list__item--replay');

    await user.click(screen.getByRole('button', { name: /demo run/i }));

    expect(onSelectLive).not.toHaveBeenCalled();
    expect(onSelectReplay).not.toHaveBeenCalled();
  });

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

  it('renders completed-run actions in a dedicated footer row layout', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            {
              run_id: 'done-1',
              problem_name: 'A Very Long Completed Run Name For Layout Testing',
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
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const { container } = render(
      <RunList
        activeRunId={null}
        mode="idle"
        onSelectLive={vi.fn()}
        onSelectReplay={vi.fn()}
      />,
    );

    expect(await screen.findByRole('button', { name: /a very long completed run name for layout testing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /replay/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

    const stylesheet = container.querySelector('style');
    expect(stylesheet?.textContent).toContain('.run-list__item {');
    expect(stylesheet?.textContent).toContain('grid-template-columns: minmax(0, 1fr);');
    expect(stylesheet?.textContent).toContain('.run-list__actions {');
    expect(stylesheet?.textContent).toContain('width: 100%;');
    expect(stylesheet?.textContent).toContain('justify-content: flex-start;');
  });

  it('hides delete for running rows and waits for confirmation before sending delete', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            { run_id: 'live-1', problem_name: 'Live Run', problem_id: 'live-run', started_at: '2026-06-05T15:00:00Z', status: 'running', final_status: null, iterations: null, pass_rate: null },
            { run_id: 'done-1', problem_name: 'Done Run', problem_id: 'done-run', started_at: '2026-06-05T15:01:00Z', status: 'completed', final_status: 'success', iterations: 3, pass_rate: 1 },
          ],
        }));
      }
      if (url === '/api/runs/done-1' && init?.method === 'DELETE') {
        return Promise.resolve(createResponse({ run_id: 'done-1', deleted: true }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RunList activeRunId={null} mode="idle" onSelectLive={vi.fn()} onSelectReplay={vi.fn()} onDeletedRun={vi.fn()} />);

    const liveRow = (await screen.findByRole('button', { name: /live run/i })).closest('article');
    expect(liveRow).not.toBeNull();
    expect(within(liveRow as HTMLElement).queryByRole('button', { name: /delete/i })).toBeNull();

    await user.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(fetchMock).not.toHaveBeenCalledWith('/api/runs/done-1', expect.objectContaining({ method: 'DELETE' }));

    await user.click(screen.getByRole('button', { name: /delete permanently/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/runs/done-1', expect.objectContaining({ method: 'DELETE' })));
  });

  it('keeps a deleted run hidden even if a later poll still returns it', async () => {
    const user = userEvent.setup();
    let pollRuns: (() => void) | null = null;
    const originalSetInterval = globalThis.setInterval;
    const originalClearInterval = globalThis.clearInterval;
    vi.stubGlobal('setInterval', ((callback: TimerHandler) => {
      pollRuns = callback as () => void;
      return 1 as unknown as ReturnType<typeof setInterval>;
    }) as typeof setInterval);
    vi.stubGlobal('clearInterval', ((_: ReturnType<typeof setInterval>) => {}) as typeof clearInterval);

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            { run_id: 'done-1', problem_name: 'Done Run', problem_id: 'done-run', started_at: '2026-06-05T15:00:00Z', status: 'completed', final_status: 'success', iterations: 3, pass_rate: 1 },
          ],
        }));
      }
      if (url === '/api/runs/done-1' && init?.method === 'DELETE') {
        return Promise.resolve(createResponse({ run_id: 'done-1', deleted: true }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<RunList activeRunId={null} mode="idle" onSelectLive={vi.fn()} onSelectReplay={vi.fn()} onDeletedRun={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: /delete/i }));
    await user.click(screen.getByRole('button', { name: /delete permanently/i }));
    await waitFor(() => expect(screen.queryByText(/done run/i)).not.toBeInTheDocument());

    await act(async () => {
      pollRuns?.();
      await Promise.resolve();
    });

    expect(fetchMock).toHaveBeenCalled();
    expect(screen.queryByText(/done run/i)).not.toBeInTheDocument();
    globalThis.setInterval = originalSetInterval;
    globalThis.clearInterval = originalClearInterval;
  });
});
