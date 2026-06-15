import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./components/Layout', () => ({
  default: ({ header, main, sidebar }: { header: React.ReactNode; main: React.ReactNode; sidebar: React.ReactNode }) => (
    <div>
      <div data-testid="layout-header">{header}</div>
      <div data-testid="layout-main">{main}</div>
      <div data-testid="layout-sidebar">{sidebar}</div>
    </div>
  ),
}));

vi.mock('./components/AlgorithmStoryCard', () => ({ default: () => <div data-testid="algorithm-story-card" /> }));
vi.mock('./components/EvidenceWorkbench', () => ({ default: () => <div data-testid="evidence-workbench" /> }));
vi.mock('./components/FailureAnalysisCard', () => ({ default: () => <div data-testid="failure-analysis-card" /> }));
vi.mock('./components/FinalSummaryCard', async () => await vi.importActual('./components/FinalSummaryCard'));
vi.mock('./components/StageDetailPanel', () => ({ default: () => <div data-testid="stage-detail-panel" /> }));

import App from './App';
import * as useRunSessionModule from './hooks/useRunSession';
import type { RunSessionState } from './state/runSessionReducer';
import * as runApiModule from './utils/runApi';

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
    this.onclose?.({ code: 1000, reason: '', wasClean: true } as CloseEvent);
  }

  emitMessage(payload: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }

  open(): void {
    this.onopen?.({ type: 'open' } as Event);
  }

  static reset(): void {
    MockWebSocket.instances = [];
  }
}

function createResponse(payload: Record<string, unknown>, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => payload,
  } as Response;
}

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('App integration', () => {
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
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('switches core dashboard chrome between English and Chinese', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs') {
        return Promise.resolve(createResponse({ runs: [] }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<App />);

    expect(screen.getByRole('button', { name: /switch language to chinese/i })).toBeInTheDocument();
    expect(screen.getByText('Current Run')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start solve/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /switch language to chinese/i }));

    expect(screen.getByRole('button', { name: /切换语言为英文/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /切换风格为明亮/ })).toBeInTheDocument();
    expect(screen.getByText('当前运行')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /开始求解/ })).toBeInTheDocument();
    expect(screen.getByText('求解旅程')).toBeInTheDocument();
  });

  it('switches dashboard theme between dark and bright and remembers the choice', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs') {
        return Promise.resolve(createResponse({ runs: [] }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    const mounted = render(<App />);

    expect(document.documentElement.dataset.dashboardTheme).toBe('dark');
    expect(screen.getByRole('button', { name: /switch theme to bright/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /switch theme to bright/i }));

    expect(document.documentElement.dataset.dashboardTheme).toBe('bright');
    expect(window.localStorage.getItem('algopilot-dashboard-theme')).toBe('bright');
    expect(screen.getByRole('button', { name: /switch theme to dark/i })).toBeInTheDocument();

    mounted.unmount();
    render(<App />);

    expect(document.documentElement.dataset.dashboardTheme).toBe('bright');
    expect(screen.getByRole('button', { name: /switch theme to dark/i })).toBeInTheDocument();
  });

  it('supports start solve, live progress, final replay-ready mode, and refresh restore', async () => {
    const user = userEvent.setup();
    let runCompleted = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Pair Sum',
              source: 'showcase',
              preview: 'Find two numbers that sum to target.',
              difficulty: 'easy',
              is_showcase: true,
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Find two numbers that sum to target.',
          public_tests: [{ input: '5\n1 2 3 4 5\n6\n', output: '1 5\n' }],
          _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
        }));
      }

      if (url === '/api/runs' && init?.method === 'POST') {
        return Promise.resolve(createResponse({ run_id: 'run-live', status: 'running' }));
      }

      if (url === '/api/runs') {
        return Promise.resolve(createResponse({
          runs: runCompleted
            ? [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'completed', final_status: 'accepted', iterations: 1, pass_rate: 1 }]
            : [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'running', final_status: null, iterations: null, pass_rate: null }],
        }));
      }

      if (url === '/api/runs/run-live') {
        return Promise.resolve(createResponse(
          runCompleted
            ? {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: 'accepted',
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'phase_start', phase: 'codegen_phase', label: 'Generating & Testing Code' }, seq: 1, timestamp: 2 },
                  { event: { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen' }, seq: 2, timestamp: 3 },
                  { event: { type: 'final', status: 'accepted', iterations: 1, passed: 3, total: 3, pass_rate: 1 }, seq: 3, timestamp: 4 },
                ],
              }
            : {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: null,
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'phase_start', phase: 'codegen_phase', label: 'Generating & Testing Code' }, seq: 1, timestamp: 2 },
                  { event: { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen' }, seq: 2, timestamp: 3 },
                ],
              },
        ));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    const mounted = render(<App />);

    await user.click(screen.getByRole('button', { name: /start solve/i }));
    await screen.findByText(/selected problem/i);
    const startSolveButtons = screen.getAllByRole('button', { name: /^start solve$/i });
    await user.click(startSolveButtons[startSolveButtons.length - 1]);

    await waitFor(() => expect(screen.getAllByText(/run-live/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    act(() => {
      MockWebSocket.instances[0].open();
    });

    act(() => {
      MockWebSocket.instances[0].emitMessage({
        type: 'phase_done',
        phase: 'abstract_phase',
        seq: 3,
        ts: 3,
        data: { tags: ['two pointers', 'greedy'], confidence: 0.88 },
      });
    });

    await waitFor(() => expect(screen.getByText('Abstract tags')).toBeInTheDocument());
    expect(screen.getByText('two pointers')).toBeInTheDocument();
    expect(screen.getByText('greedy')).toBeInTheDocument();
    expect(screen.getByText('88% confidence')).toBeInTheDocument();

    await waitFor(() => expect(screen.getAllByText(/compile the draft/i).length).toBeGreaterThan(0));
    expect(screen.getAllByText('showcase').length).toBeGreaterThan(0);

    act(() => {
      MockWebSocket.instances[0].emitMessage({
        type: 'artifact_snapshot',
        data: {
          status: 'pending',
          iteration: 1,
          tests: {
            public_tests: [],
            generated_tests: [],
            passed_tests: 2,
            total_tests: 3,
            pass_rate: 2 / 3,
            full_testgen_completed: true,
            trust_tiers: {},
          },
          hack: {
            result: null,
            passed: null,
            round: null,
            failures: [],
            generator_failure_kind: null,
            generator_failure_reason: null,
          },
          execution_log_tail: ['Compile the draft'],
        },
      });
    });

    await waitFor(() => expect(screen.getByText('2/3')).toBeInTheDocument());

    act(() => {
      runCompleted = true;
      MockWebSocket.instances[0].emitMessage({
        type: 'final',
        status: 'accepted',
        iterations: 1,
        passed: 3,
        total: 3,
        pass_rate: 1,
        prompt_tokens: 10,
        completion_tokens: 5,
      });
    });

    await waitFor(() => expect(screen.getAllByText(/replay/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText(/replay progress/i)).toBeInTheDocument());
    expect(JSON.parse(window.localStorage.getItem('algopilot.dashboard.lastRun') || 'null')).toMatchObject({
      runId: 'run-live',
      mode: 'replay',
    });

    mounted.unmount();

    render(<App />);

    await waitFor(() => expect(screen.getAllByText(/run-live/i).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText(/replay progress/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText(/compile the draft/i).length).toBeGreaterThan(0));
  });

  it('hides the algorithm story card after a non-success completed run', async () => {
    const user = userEvent.setup();
    let runFailed = false;

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Pair Sum',
              source: 'showcase',
              preview: 'Find two numbers that sum to target.',
              difficulty: 'easy',
              is_showcase: true,
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Find two numbers that sum to target.',
          public_tests: [],
          _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
        }));
      }

      if (url === '/api/runs' && init?.method === 'POST') {
        return Promise.resolve(createResponse({ run_id: 'run-live', status: 'running' }));
      }

      if (url === '/api/runs') {
        return Promise.resolve(createResponse({
          runs: runFailed
            ? [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'completed', final_status: 'max_iterations', iterations: 3, pass_rate: 0 }]
            : [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'running', final_status: null, iterations: null, pass_rate: null }],
        }));
      }

      if (url === '/api/runs/run-live') {
        return Promise.resolve(createResponse(
          runFailed
            ? {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: 'max_iterations',
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'artifact_snapshot', data: { algorithm_visualization: { supported: true, family: 'bfs', mode: 'teaching', title: 'Story', summary: 'summary', sample_source: 'public', sample_focus: '', sample_input: '', sample_output: '', steps: [{ step: 1, label: 'step', caption: 'caption' }] } } }, seq: 1, timestamp: 2 },
                  { event: { type: 'final', status: 'max_iterations' }, seq: 2, timestamp: 3 },
                ],
              }
            : {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: null,
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'artifact_snapshot', data: { algorithm_visualization: { supported: true, family: 'bfs', mode: 'teaching', title: 'Story', summary: 'summary', sample_source: 'public', sample_focus: '', sample_input: '', sample_output: '', steps: [{ step: 1, label: 'step', caption: 'caption' }] } } }, seq: 1, timestamp: 2 },
                ],
              },
        ));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await user.click(screen.getByRole('button', { name: /start solve/i }));
    const startSolveButtons = await screen.findAllByRole('button', { name: /^start solve$/i });
    await user.click(startSolveButtons[startSolveButtons.length - 1]);

    await waitFor(() => expect(screen.getByTestId('algorithm-story-card')).toBeInTheDocument());

    runFailed = true;
    act(() => {
      MockWebSocket.instances[0].emitMessage({ type: 'final', status: 'max_iterations' });
    });

    await waitFor(() => expect(screen.queryByTestId('algorithm-story-card')).not.toBeInTheDocument());
  });

  it('keeps the algorithm story card visible after a successful completed run', async () => {
    const user = userEvent.setup();
    let runCompleted = false;

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url === '/api/problems') {
        return Promise.resolve(createResponse({
          problems: [
            {
              id: 'p1',
              name: 'Pair Sum',
              source: 'showcase',
              preview: 'Find two numbers that sum to target.',
              difficulty: 'easy',
              is_showcase: true,
            },
          ],
        }));
      }

      if (url === '/api/problems/p1') {
        return Promise.resolve(createResponse({
          problem_id: 'p1',
          description: 'Find two numbers that sum to target.',
          public_tests: [],
          _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
        }));
      }

      if (url === '/api/runs' && init?.method === 'POST') {
        return Promise.resolve(createResponse({ run_id: 'run-live', status: 'running' }));
      }

      if (url === '/api/runs') {
        return Promise.resolve(createResponse({
          runs: runCompleted
            ? [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'completed', final_status: 'accepted', iterations: 3, pass_rate: 1 }]
            : [{ run_id: 'run-live', problem_name: 'Pair Sum', status: 'running', final_status: null, iterations: null, pass_rate: null }],
        }));
      }

      if (url === '/api/runs/run-live') {
        return Promise.resolve(createResponse(
          runCompleted
            ? {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: 'accepted',
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'artifact_snapshot', data: { algorithm_visualization: { supported: true, family: 'bfs', mode: 'teaching', title: 'Story', summary: 'summary', sample_source: 'public', sample_focus: '', sample_input: '', sample_output: '', steps: [{ step: 1, label: 'step', caption: 'caption' }] } } }, seq: 1, timestamp: 2 },
                  { event: { type: 'final', status: 'accepted' }, seq: 2, timestamp: 3 },
                ],
              }
            : {
                run_id: 'run-live',
                problem_id: 'p1',
                problem: {
                  description: 'Find two numbers that sum to target.',
                  _metadata: { name: 'Pair Sum', source: 'showcase', is_showcase: true },
                },
                config: { max_iterations: 5 },
                final_status: null,
                events: [
                  { event: { type: 'solve_start', problem_id: 'p1', problem_name: 'Pair Sum' }, seq: 0, timestamp: 1 },
                  { event: { type: 'artifact_snapshot', data: { algorithm_visualization: { supported: true, family: 'bfs', mode: 'teaching', title: 'Story', summary: 'summary', sample_source: 'public', sample_focus: '', sample_input: '', sample_output: '', steps: [{ step: 1, label: 'step', caption: 'caption' }] } } }, seq: 1, timestamp: 2 },
                ],
              },
        ));
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await user.click(screen.getByRole('button', { name: /start solve/i }));
    const startSolveButtons = await screen.findAllByRole('button', { name: /^start solve$/i });
    await user.click(startSolveButtons[startSolveButtons.length - 1]);

    await waitFor(() => expect(screen.getByTestId('algorithm-story-card')).toBeInTheDocument());

    runCompleted = true;
    act(() => {
      MockWebSocket.instances[0].emitMessage({ type: 'final', status: 'accepted' });
    });

    await waitFor(() => expect(screen.getAllByText(/replay/i).length).toBeGreaterThan(0));
    expect(screen.getByTestId('algorithm-story-card')).toBeInTheDocument();
  });

  it('does not carry interrupt pending state to a different live run', async () => {
    const user = userEvent.setup();
    const pendingCancel = createDeferred<Record<string, unknown>>();
    const sessionBase = {
      hydrationStatus: 'ready' as const,
      wsStatus: 'connected' as const,
      shouldConnectLive: true,
      selectedStageId: null,
      selectedTimelineId: null,
      replayCursor: 1,
    };
    let session: RunSessionState = {
      ...sessionBase,
      runId: 'run-a',
      mode: 'live' as const,
      runDetail: {
        runId: 'run-a',
        problemId: 'a',
        problem: { description: 'A', _metadata: { name: 'Run A' } },
        config: {},
        finalStatus: null,
      },
      events: [{ type: 'solve_start', problem_id: 'a', problem_name: 'Run A', seq: 0, ts: 1 }],
    };

    vi.spyOn(useRunSessionModule, 'useRunSession').mockImplementation(() => ({
      clearSession: vi.fn(),
      dropRun: vi.fn(),
      reconnect: vi.fn(async () => false),
      restoreLatestRun: vi.fn(async () => false),
      selectLiveRun: vi.fn(async () => true),
      selectReplayRun: vi.fn(async () => true),
      session,
      setReplayCursor: vi.fn(),
      setSelectedStageId: vi.fn(),
      setSelectedTimelineId: vi.fn(),
    }));
    vi.spyOn(runApiModule, 'cancelRun').mockImplementation(() => pendingCancel.promise);

    const view = render(<App />);

    await waitFor(() => expect(screen.getByRole('button', { name: /^interrupt$/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^interrupt$/i }));
    expect(screen.getByRole('button', { name: /interrupting/i })).toBeDisabled();

    session = {
      ...sessionBase,
      runId: 'run-b',
      mode: 'live',
      runDetail: {
        runId: 'run-b',
        problemId: 'b',
        problem: { description: 'B', _metadata: { name: 'Run B' } },
        config: {},
        finalStatus: null,
      },
      events: [{ type: 'solve_start', problem_id: 'b', problem_name: 'Run B', seq: 0, ts: 1 }],
    };
    view.rerender(<App />);
    expect(screen.getAllByText(/run b/i).length).toBeGreaterThan(0);

    const interruptButton = screen.getByRole('button', { name: /^interrupt$/i });
    expect(interruptButton).not.toBeDisabled();

    pendingCancel.resolve({ run_id: 'run-a', cancelled: true, final_status: 'cancelled' });
  });

  it('does not let a failed earlier interrupt clear the pending state of a newer live run', async () => {
    const user = userEvent.setup();
    const cancelA = createDeferred<Record<string, unknown>>();
    const cancelB = createDeferred<Record<string, unknown>>();
    const sessionBase = {
      hydrationStatus: 'ready' as const,
      wsStatus: 'connected' as const,
      shouldConnectLive: true,
      selectedStageId: null,
      selectedTimelineId: null,
      replayCursor: 1,
    };
    let session: RunSessionState = {
      ...sessionBase,
      runId: 'run-a',
      mode: 'live' as const,
      runDetail: {
        runId: 'run-a',
        problemId: 'a',
        problem: { description: 'A', _metadata: { name: 'Run A' } },
        config: {},
        finalStatus: null,
      },
      events: [{ type: 'solve_start', problem_id: 'a', problem_name: 'Run A', seq: 0, ts: 1 }],
    };

    vi.spyOn(useRunSessionModule, 'useRunSession').mockImplementation(() => ({
      clearSession: vi.fn(),
      dropRun: vi.fn(),
      reconnect: vi.fn(async () => false),
      restoreLatestRun: vi.fn(async () => false),
      selectLiveRun: vi.fn(async () => true),
      selectReplayRun: vi.fn(async () => true),
      session,
      setReplayCursor: vi.fn(),
      setSelectedStageId: vi.fn(),
      setSelectedTimelineId: vi.fn(),
    }));

    vi.spyOn(runApiModule, 'cancelRun').mockImplementation((runId: string) => {
      if (runId === 'run-a') return cancelA.promise;
      if (runId === 'run-b') return cancelB.promise;
      throw new Error(`Unexpected runId: ${runId}`);
    });

    const view = render(<App />);

    await waitFor(() => expect(screen.getByRole('button', { name: /^interrupt$/i })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^interrupt$/i }));
    expect(screen.getByRole('button', { name: /interrupting/i })).toBeDisabled();

    session = {
      ...sessionBase,
      runId: 'run-b',
      mode: 'live',
      runDetail: {
        runId: 'run-b',
        problemId: 'b',
        problem: { description: 'B', _metadata: { name: 'Run B' } },
        config: {},
        finalStatus: null,
      },
      events: [{ type: 'solve_start', problem_id: 'b', problem_name: 'Run B', seq: 0, ts: 1 }],
    };
    view.rerender(<App />);
    await user.click(screen.getByRole('button', { name: /^interrupt$/i }));
    expect(screen.getByRole('button', { name: /interrupting/i })).toBeDisabled();

    cancelA.reject(new Error('cancel failed'));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole('button', { name: /interrupting/i })).toBeDisabled();

    cancelB.resolve({ run_id: 'run-b', cancelled: true, final_status: 'cancelled' });
  });

  it('routes deleting the active replay run through dropRun', async () => {
    const user = userEvent.setup();
    const dropRun = vi.fn();

    vi.spyOn(useRunSessionModule, 'useRunSession').mockImplementation(() => ({
      clearSession: vi.fn(),
      dropRun,
      reconnect: vi.fn(async () => false),
      restoreLatestRun: vi.fn(async () => false),
      selectLiveRun: vi.fn(async () => true),
      selectReplayRun: vi.fn(async () => true),
      session: {
        runId: 'run-delete',
        mode: 'replay',
        hydrationStatus: 'ready',
        wsStatus: 'disconnected',
        runDetail: {
          runId: 'run-delete',
          problemId: 'p1',
          problem: { description: 'demo', _metadata: { name: 'Delete Run' } },
          config: {},
          finalStatus: 'success',
        },
        events: [
          { type: 'solve_start', problem_id: 'p1', problem_name: 'Delete Run', seq: 0, ts: 1 },
          { type: 'final', status: 'success', seq: 1, ts: 2 },
        ],
        shouldConnectLive: false,
        selectedStageId: null,
        selectedTimelineId: null,
        replayCursor: 2,
      },
      setReplayCursor: vi.fn(),
      setSelectedStageId: vi.fn(),
      setSelectedTimelineId: vi.fn(),
    }));

    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            {
              run_id: 'run-delete',
              problem_name: 'Delete Run',
              problem_id: 'p1',
              started_at: '2026-06-07T00:00:00Z',
              status: 'completed',
              final_status: 'success',
              iterations: 1,
              pass_rate: 1,
            },
          ],
        }));
      }
      if (url === '/api/runs/run-delete' && init?.method === 'DELETE') {
        return Promise.resolve(createResponse({ run_id: 'run-delete', deleted: true }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<App />);

    await waitFor(() => expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument(), {
      timeout: 6000,
    });
    await user.click(screen.getByRole('button', { name: /^delete$/i }));
    await user.click(screen.getByRole('button', { name: /delete permanently/i }));

    await waitFor(() => expect(dropRun).toHaveBeenCalledWith('run-delete'));
  });

  it('renders the full problem statement before the unsupported story placeholder on the active run page', async () => {
    vi.spyOn(useRunSessionModule, 'useRunSession').mockImplementation(() => ({
      clearSession: vi.fn(),
      dropRun: vi.fn(),
      reconnect: vi.fn(async () => false),
      restoreLatestRun: vi.fn(async () => false),
      selectLiveRun: vi.fn(async () => true),
      selectReplayRun: vi.fn(async () => true),
      session: {
        runId: 'run-story',
        mode: 'live',
        hydrationStatus: 'ready',
        wsStatus: 'connected',
        runDetail: {
          runId: 'run-story',
          problemId: 'p1',
          problem: {
            description: `Problem
Find the shortest path in the graph.

Input Format
n m

Output Format
minimum distance`,
            _metadata: {
              name: 'Shortest Path',
              source: 'showcase',
              family: 'graphs',
            },
            public_tests: [{ input: '1 0', output: '0' }],
          },
          config: { max_iterations: 4 },
          finalStatus: null,
        },
        events: [
          { type: 'solve_start', problem_id: 'p1', problem_name: 'Shortest Path', seq: 0, ts: 1 },
          { type: 'phase_start', phase: 'plan', seq: 1, ts: 2 },
          {
            type: 'artifact_snapshot',
            seq: 2,
            ts: 3,
            data: {
              algorithm_visualization: {
                supported: false,
                family: 'unsupported',
                mode: 'teaching',
                sample_source: 'public',
                sample_focus: '',
                sample_input: '',
                sample_output: '',
                title: 'Unsupported story',
                summary: 'No supported story.',
                steps: [],
                fallback_text: '',
              },
            },
          },
        ],
        shouldConnectLive: true,
        selectedStageId: null,
        selectedTimelineId: null,
        replayCursor: 3,
      },
      setReplayCursor: vi.fn(),
      setSelectedStageId: vi.fn(),
      setSelectedTimelineId: vi.fn(),
    }));
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/runs') {
        return Promise.resolve(createResponse({ runs: [] }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    }));

    render(<App />);

    const main = screen.getByTestId('layout-main');
    const problemStatement = await screen.findByText('Problem Statement');
    const unsupportedPlaceholder = await screen.findByText('No family-level walkthrough is available for this problem.');

    expect(screen.getByText('AlgoPilot Run Context')).toBeInTheDocument();
    expect(problemStatement).toBeInTheDocument();
    expect(unsupportedPlaceholder).toBeInTheDocument();
    expect(main).toContainElement(problemStatement);
    expect(main).toContainElement(unsupportedPlaceholder);
    expect(problemStatement.compareDocumentPosition(unsupportedPlaceholder) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('interrupts a live run into cancelled replay and clears the session when that replay is deleted', async () => {
    const user = userEvent.setup();
    let runState: 'running' | 'cancelled' | 'deleted' = 'running';
    const cancelDeferred = createDeferred<Response>();

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
        return cancelDeferred.promise;
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
    const startSolveButtons = await screen.findAllByRole('button', { name: /^start solve$/i });
    await user.click(startSolveButtons[startSolveButtons.length - 1]);
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1));

    act(() => {
      MockWebSocket.instances[0].open();
    });

    await user.click(await screen.findByRole('button', { name: /^interrupt$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/runs/run-live/cancel',
      expect.objectContaining({ method: 'POST' }),
    ));

    runState = 'cancelled';
    await act(async () => {
      cancelDeferred.resolve(createResponse({ run_id: 'run-live', cancelled: true, final_status: 'cancelled' }));
      await Promise.resolve();
    });

    await waitFor(() => expect(screen.getAllByText(/replay/i).length).toBeGreaterThan(0));
    expect(screen.getByText(/The run was interrupted by the user/i)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument(), {
      timeout: 6000,
    });
    await user.click(screen.getByRole('button', { name: /^delete$/i }));
    await user.click(screen.getByRole('button', { name: /delete permanently/i }));

    await waitFor(() => expect(screen.getAllByText(/No active run/i).length).toBeGreaterThan(0));
  }, 12000);
});
