import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DashboardI18nProvider, useI18n } from '../i18n';
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

interface ProblemPanelRenderProps {
  onSubmit: (problem: Record<string, unknown>, config: Record<string, unknown>) => Promise<boolean>;
  onClose: () => void;
}

function ZhProblemPanel(props: ProblemPanelRenderProps) {
  const { setLanguage } = useI18n();

  useEffect(() => {
    setLanguage('zh');
  }, [setLanguage]);

  return <ProblemPanel {...props} />;
}

function renderZhProblemPanel(props: ProblemPanelRenderProps) {
  return render(
    <DashboardI18nProvider>
      <ZhProblemPanel {...props} />
    </DashboardI18nProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ProblemPanel', () => {
  it('localizes the problem panel chrome in Chinese mode', async () => {
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
          description: 'Demo statement for preview',
          public_tests: [],
          _metadata: { name: 'Demo', source: 'sample', difficulty: 'easy' },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderZhProblemPanel({ onSubmit: vi.fn(), onClose: vi.fn() });

    expect(await screen.findByRole('heading', { name: '启动 AlgoPilot 运行' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'AlgoPilot 题库' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('按名称或来源搜索...')).toBeInTheDocument();
    expect(screen.getByText('1 道示例题')).toBeInTheDocument();
    expect(screen.getByText('0 道已保存自定义题')).toBeInTheDocument();
    expect(screen.getByText('已选择题目')).toBeInTheDocument();
    expect(screen.queryByText('Start an AlgoPilot Run')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '自定义题目' }));

    expect(screen.getByText('自定义编写')).toBeInTheDocument();
    expect(screen.getByText('题目标题')).toBeInTheDocument();
    expect(screen.getByText('来源标签')).toBeInTheDocument();
    expect(screen.getByText('题目描述')).toBeInTheDocument();
    expect(screen.getByText('公开测试')).toBeInTheDocument();
    expect(screen.getByText('保存到本地题库后再求解')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存并开始求解' })).toBeInTheDocument();
  });

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

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Demo statement for preview',
          public_tests: [{ input: '1\n', output: '1\n' }],
          _metadata: { name: 'Demo', source: 'sample', difficulty: 'easy' },
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

    const onSubmit = vi.fn().mockResolvedValue(true);
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

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Demo statement for preview',
          public_tests: [{ input: '1\n', output: '1\n' }],
          _metadata: { name: 'Demo', source: 'sample', difficulty: 'easy' },
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
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
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

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Demo statement for preview',
          public_tests: [{ input: '1\n', output: '1\n' }],
          _metadata: { name: 'Demo', source: 'sample', difficulty: 'easy' },
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

  it('fetches selected library detail and renders a compact full statement preview in browse mode', async () => {
    const detailRequest = createDeferred<Response>();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Demo',
              source: 'sample',
              preview: 'short preview from list',
              difficulty: 'easy',
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return detailRequest.promise;
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ProblemPanel onSubmit={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByText(/loading full statement/i)).toBeInTheDocument();

    detailRequest.resolve(createResponse({
      problem_id: 'p1',
      description: `Problem
Solve the array challenge.

Input Format
The first line contains n.

Output Format
Print the best answer.

Sample Input 1
3
1 2 3

Sample Output 1
6`,
      public_tests: [{ input: '3\n1 2 3', output: '6' }],
      _metadata: {
        name: 'Demo',
        source: 'sample',
        difficulty: 'easy',
      },
    }));

    const preview = await screen.findByText('Problem Preview');
    expect(preview).toBeInTheDocument();
    expect(screen.getByText('Solve the array challenge.')).toBeInTheDocument();
    expect(screen.getByText('Input Format')).toBeInTheDocument();
    expect(screen.getByText('Output Format')).toBeInTheDocument();
  });

  it('stops using the short list preview text as the main browse preview once full detail loads', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Demo',
              source: 'sample',
              preview: 'short preview from list',
              difficulty: 'easy',
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: `Problem
Full statement body replaces the old preview.

Constraints
1 <= n <= 100`,
          public_tests: [],
          _metadata: {
            name: 'Demo',
            source: 'sample',
            difficulty: 'easy',
          },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ProblemPanel onSubmit={vi.fn()} onClose={vi.fn()} />);

    const previewPanel = (await screen.findByText('Selected Problem')).closest('.pp-preview');
    expect(previewPanel).not.toBeNull();
    expect(await screen.findByText('Full statement body replaces the old preview.')).toBeInTheDocument();
    expect(screen.getByText('short preview from list')).toBeInTheDocument();
    expect(within(previewPanel as HTMLElement).queryByText('short preview from list')).not.toBeInTheDocument();
  });

  it('refreshes the browse preview detail after updating a saved custom problem', async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'saved-problem.json',
              name: 'Saved Problem',
              source: 'custom',
              preview: 'old preview',
              difficulty: 'medium',
              is_custom: true,
            },
          ],
        }));
      }

      if (url === '/api/problems/saved-problem.json') {
        return Promise.resolve(createResponse({
          problem_id: 'saved-problem',
          description: 'Problem\nOld saved statement.',
          public_tests: [{ input: '1\n', output: '1\n' }],
          _metadata: { name: 'Saved Problem', source: 'custom', difficulty: 'medium', custom: true },
        }));
      }

      if (url === '/api/problems/custom/saved-problem.json' && init?.method === 'PUT') {
        return Promise.resolve(createResponse({
          filename: 'saved-problem.json',
          problem: {
            problem_id: 'saved-problem',
            description: 'Problem\nUpdated saved statement.',
            public_tests: [{ input: '2\n', output: '2\n' }],
            _metadata: { name: 'Saved Problem', source: 'custom', difficulty: 'medium', custom: true },
          },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const onSubmit = vi.fn().mockResolvedValue(true);
    render(<ProblemPanel onSubmit={onSubmit} onClose={vi.fn()} />);

    expect(await screen.findByText('Old saved statement.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /manage algopilot library/i }));
    await user.click(await screen.findByRole('button', { name: /rename \/ edit/i }));

    const statementField = await screen.findByLabelText(/problem statement/i);
    await user.clear(statementField);
    await user.type(statementField, 'Updated saved statement.');

    await user.click(screen.getByRole('button', { name: /update & start solve/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole('button', { name: /^algopilot library$/i }));

    expect(await screen.findByText('Updated saved statement.')).toBeInTheDocument();
    expect(screen.queryByText('Old saved statement.')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('uses theme tokens for problem panel surfaces instead of hard-coded dark surfaces', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Demo',
              source: 'sample',
              preview: 'demo preview',
              difficulty: 'easy',
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Demo statement for preview',
          public_tests: [],
          _metadata: { name: 'Demo', source: 'sample', difficulty: 'easy' },
        }));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ProblemPanel onSubmit={vi.fn()} onClose={vi.fn()} />);

    await screen.findByText('Demo');
    const panelStyles = Array.from(document.querySelectorAll('style'))
      .map((style) => style.textContent || '')
      .find((content) => content.includes('.pp-modal'));

    expect(panelStyles).toContain('var(--color-problem-panel-modal-bg)');
    expect(panelStyles).toContain('var(--color-problem-panel-item-bg)');
    expect(panelStyles).toContain('var(--color-problem-panel-selected-bg)');
    expect(panelStyles).toContain('var(--color-problem-panel-preview-bg)');
    expect(panelStyles).not.toContain('rgba(14, 19, 28');
    expect(panelStyles).not.toContain('rgba(7, 11, 17');
    expect(panelStyles).not.toContain('rgba(255,255,255,0.04)');
    expect(panelStyles).not.toContain('rgba(255,255,255,0.03)');
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
