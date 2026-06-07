import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ProblemPanel from './ProblemPanel';

interface Deferred<T> {
  promise: Promise<T>;
  reject: (reason?: unknown) => void;
  resolve: (value: T | PromiseLike<T>) => void;
}

function createDeferred<T>(): Deferred<T> {
  let resolve!: Deferred<T>['resolve'];
  let reject!: Deferred<T>['reject'];
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return { promise, reject, resolve };
}

function createResponse(payload: Record<string, unknown>, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => payload,
  } as Response;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ProblemPanel', () => {
  it('loads library problems, searches Codeforces, and imports a problem for solving', async () => {
    const user = userEvent.setup();
    const importedProblem = {
      problem_id: 'codeforces_1575_C',
      description: 'Cyclic Sum statement',
      public_tests: [
        { input: '1', output: '1' },
      ],
      _metadata: {
        source: 'codeforces',
        platform: 'codeforces',
        question_id: 'codeforces_1575_C',
        name: 'Cyclic Sum',
      },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            { id: 'p1', name: 'Demo', source: 'sample', preview: 'demo preview', difficulty: 'easy' },
          ],
        }));
      }

      if (url.startsWith('/api/sources/codeforces/search?')) {
        const parsedUrl = new URL(url, 'http://localhost');
        expect(parsedUrl.searchParams.get('q')).toBe('1575 C');

        return Promise.resolve(createResponse({
          results: [
            {
              contest_id: 1575,
              index: 'C',
              name: 'Cyclic Sum',
              rating: 2100,
              tags: ['math', 'dp'],
              url: 'https://codeforces.com/contest/1575/problem/C',
              problem_id: 'codeforces_1575_C',
            },
          ],
          cache_status: 'ready',
        }));
      }

      if (url === '/api/sources/codeforces/import' && init?.method === 'POST') {
        expect(init.headers).toEqual(expect.objectContaining({ 'Content-Type': 'application/json' }));
        expect(JSON.parse(String(init.body))).toEqual({
          contest_id: 1575,
          index: 'C',
          url: 'https://codeforces.com/contest/1575/problem/C',
        });

        return Promise.resolve(createResponse({
          problem_id: 'codeforces_1575_C',
          filename: 'codeforces_1575_C.json',
          problem: importedProblem,
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSubmit = vi.fn().mockResolvedValue(false);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    expect(await screen.findByText('Demo')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /codeforces/i }));
    await user.type(screen.getByRole('textbox', { name: /search codeforces/i }), '1575 C');
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    expect(await screen.findByText('Cyclic Sum')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /import and solve/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        problem_id: 'codeforces_1575_C',
        _metadata: expect.objectContaining({ source: 'codeforces' }),
      }),
      expect.any(Object),
    );
  });

  it('re-enables Codeforces import after a successful solve start when the panel stays mounted', async () => {
    const user = userEvent.setup();
    const importedProblem = {
      problem_id: 'codeforces_1575_C',
      description: 'Cyclic Sum statement',
      public_tests: [
        { input: '1', output: '1' },
      ],
      _metadata: {
        source: 'codeforces',
        platform: 'codeforces',
        question_id: 'codeforces_1575_C',
        name: 'Cyclic Sum',
      },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            { id: 'p1', name: 'Demo', source: 'sample', preview: 'demo preview', difficulty: 'easy' },
          ],
        }));
      }

      if (url.startsWith('/api/sources/codeforces/search?')) {
        return Promise.resolve(createResponse({
          results: [
            {
              contest_id: 1575,
              index: 'C',
              name: 'Cyclic Sum',
              rating: 2100,
              tags: ['math', 'dp'],
              url: 'https://codeforces.com/contest/1575/problem/C',
              problem_id: 'codeforces_1575_C',
            },
          ],
          cache_status: 'ready',
        }));
      }

      if (url === '/api/sources/codeforces/import' && init?.method === 'POST') {
        return Promise.resolve(createResponse({
          problem_id: 'codeforces_1575_C',
          filename: 'codeforces_1575_C.json',
          problem: importedProblem,
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const submission = createDeferred<boolean>();
    const onSubmit = vi.fn().mockReturnValue(submission.promise);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: /codeforces/i }));
    await user.type(screen.getByRole('textbox', { name: /search codeforces/i }), '1575 C');
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    const importButton = await screen.findByRole('button', { name: /import and solve/i });
    await user.click(importButton);

    await waitFor(() => expect(importButton).toBeDisabled());
    expect(onSubmit).toHaveBeenCalledTimes(1);

    submission.resolve(true);

    await waitFor(() => expect(screen.getByRole('button', { name: /import and solve/i })).not.toBeDisabled());
  });

  it('re-enables Codeforces import and shows an alert when submit rejects after import', async () => {
    const user = userEvent.setup();
    const importedProblem = {
      problem_id: 'codeforces_1575_C',
      description: 'Cyclic Sum statement',
      public_tests: [
        { input: '1', output: '1' },
      ],
      _metadata: {
        source: 'codeforces',
        platform: 'codeforces',
        question_id: 'codeforces_1575_C',
        name: 'Cyclic Sum',
      },
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            { id: 'p1', name: 'Demo', source: 'sample', preview: 'demo preview', difficulty: 'easy' },
          ],
        }));
      }

      if (url.startsWith('/api/sources/codeforces/search?')) {
        return Promise.resolve(createResponse({
          results: [
            {
              contest_id: 1575,
              index: 'C',
              name: 'Cyclic Sum',
              rating: 2100,
              tags: ['math', 'dp'],
              url: 'https://codeforces.com/contest/1575/problem/C',
              problem_id: 'codeforces_1575_C',
            },
          ],
          cache_status: 'ready',
        }));
      }

      if (url === '/api/sources/codeforces/import' && init?.method === 'POST') {
        return Promise.resolve(createResponse({
          problem_id: 'codeforces_1575_C',
          filename: 'codeforces_1575_C.json',
          problem: importedProblem,
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSubmit = vi.fn().mockRejectedValueOnce(new Error('boom'));
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: /codeforces/i }));
    await user.type(screen.getByRole('textbox', { name: /search codeforces/i }), '1575 C');
    await user.click(screen.getByRole('button', { name: /^search$/i }));

    await user.click(await screen.findByRole('button', { name: /import and solve/i }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('alert')).toHaveTextContent(/boom/i);
    await waitFor(() => expect(screen.getByRole('button', { name: /import and solve/i })).not.toBeDisabled());
  });

  it('re-enables Start Solve when onSubmit reports failure', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            { id: 'p1', name: 'Demo', source: 'sample', preview: 'demo preview', difficulty: 'easy' },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'demo problem',
          public_tests: [],
          _metadata: { name: 'Demo', source: 'sample' },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSubmit = vi.fn().mockResolvedValue(false);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    const button = await screen.findByRole('button', { name: /^start solve$/i });
    await user.click(button);

    expect(onSubmit).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it('shows a save error when saving a custom problem returns a non-ok response', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({ problems: [] }));
      }

      if (url === '/api/problems/custom' && init?.method === 'POST') {
        return Promise.resolve(createResponse(
          { detail: 'Failed to save custom problem' },
          { ok: false, status: 500 },
        ));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSubmit = vi.fn().mockResolvedValue(true);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: /custom problem/i }));
    await user.type(screen.getByLabelText(/problem statement/i), 'Design a solver for custom input.');

    const button = screen.getByRole('button', { name: /save & start solve/i });
    await user.click(button);

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent(/failed to save custom problem/i);
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it('awaits manage-page solve and keeps the action disabled until the submission settles', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'saved-problem.json',
              name: 'Saved Problem',
              source: 'custom',
              preview: 'saved preview',
              difficulty: 'medium',
              is_custom: true,
            },
          ],
        }));
      }

      if (url === '/api/problems/saved-problem.json') {
        return Promise.resolve(createResponse({
          problem_id: 'saved-problem',
          description: 'saved body',
          public_tests: [],
          _metadata: { name: 'Saved Problem', source: 'custom' },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const submission = createDeferred<boolean>();
    const onSubmit = vi.fn().mockReturnValue(submission.promise);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    await user.click(await screen.findByRole('button', { name: /manage algopilot library/i }));
    const solveButton = await screen.findByRole('button', { name: /solve now/i });

    await user.click(solveButton);

    await waitFor(() => expect(solveButton).toBeDisabled());
    expect(onSubmit).toHaveBeenCalledTimes(1);

    await user.click(solveButton);
    expect(onSubmit).toHaveBeenCalledTimes(1);

    submission.resolve(false);

    await waitFor(() => expect(solveButton).not.toBeDisabled());
  });
});
