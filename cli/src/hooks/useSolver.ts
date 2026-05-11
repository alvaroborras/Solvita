import { useEffect, useReducer, useRef, type Dispatch } from 'react';
import { execa, type ResultPromise } from 'execa';
import type {
  SolvitaEvent,
  SolverState,
  PhaseState,
  SolveOptions,
  FinalEvent,
  PhaseData,
  PhaseCodegenData,
} from '../types.js';

// ─── State reducer ────────────────────────────────────────────────────────────

type Action =
  | { type: 'PHASE_START'; phase: string; label: string }
  | { type: 'PHASE_DONE'; phase: string; data: PhaseData }
  | { type: 'FINAL'; event: FinalEvent }
  | { type: 'SOLUTION_SAVED'; path: string }
  | { type: 'ERROR'; message: string }
  | { type: 'DONE' };

function makePhaseDetail(phase: string, data: PhaseData): string {
  if (phase === 'abstract_phase') {
    const d = data as { tags?: string[]; confidence?: number };
    const tags = (d.tags ?? []).join(', ') || '—';
    const conf = d.confidence != null ? `conf: ${(d.confidence * 100).toFixed(0)}%` : '';
    return [tags, conf].filter(Boolean).join('  ');
  }
  if (phase === 'testgen_phase') {
    const d = data as { test_count?: number };
    return `${d.test_count ?? 0} test cases`;
  }
  if (phase === 'solver_skill_plan' || phase === 'solver_skill_plan_ensemble') {
    const d = data as { algorithm?: string };
    return d.algorithm || '';
  }
  if (phase === 'codegen_phase') {
    const d = data as PhaseCodegenData;
    const compile = d.compile_success ? 'compiled' : 'compile failed';
    const tests =
      d.total > 0
        ? `${d.passed}/${d.total} (${(d.pass_rate * 100).toFixed(0)}%)`
        : '—';
    return `iter ${d.iteration}  ${compile}  tests: ${tests}`;
  }
  if (phase === 'hacker_phase') {
    const d = data as { hack_passed?: boolean; hack_round?: number };
    return d.hack_passed ? `${d.hack_round ?? 1} round(s) — all clear` : 'bug found — looping back';
  }
  return '';
}

function phaseReducer(state: SolverState, action: Action): SolverState {
  switch (action.type) {
    case 'PHASE_START': {
      const existing = state.phases.find((p) => p.key === action.phase);
      if (existing) {
        return {
          ...state,
          phases: state.phases.map((p) =>
            p.key === action.phase ? { ...p, status: 'running', detail: '' } : p,
          ),
        };
      }
      const newPhase: PhaseState = {
        key: action.phase,
        label: action.label,
        status: 'running',
        detail: '',
      };
      return { ...state, phases: [...state.phases, newPhase] };
    }
    case 'PHASE_DONE': {
      const detail = makePhaseDetail(action.phase, action.data);
      return {
        ...state,
        phases: state.phases.map((p) =>
          p.key === action.phase ? { ...p, status: 'done', detail } : p,
        ),
      };
    }
    case 'FINAL':
      return { ...state, finalEvent: action.event };
    case 'SOLUTION_SAVED':
      return { ...state, solutionPath: action.path };
    case 'ERROR':
      return { ...state, errorMessage: action.message, running: false };
    case 'DONE':
      return { ...state, running: false };
    default:
      return state;
  }
}

const INITIAL_STATE: SolverState = {
  phases: [],
  finalEvent: null,
  solutionPath: null,
  errorMessage: null,
  running: true,
};

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSolver(options: SolveOptions) {
  const [state, dispatch] = useReducer(phaseReducer, INITIAL_STATE);
  const procRef = useRef<ResultPromise | null>(null);
  const bufRef = useRef('');

  useEffect(() => {
    const { projectRoot, inputFile, output, maxIterations, pythonBin } = options;

    const args = [
      'main.py',
      '--input',
      inputFile,
      '--output',
      output,
      '--max-iterations',
      String(maxIterations),
      '--stream-events',
    ];

    const proc = execa(pythonBin, args, {
      cwd: projectRoot,
      // stdout carries NDJSON events; stderr goes to log file (handled by Python)
      stdout: 'pipe',
      stderr: 'inherit',
      reject: false,
    });
    procRef.current = proc;

    // Parse incoming stdout chunks into NDJSON lines
    proc.stdout?.on('data', (chunk: Buffer) => {
      bufRef.current += chunk.toString('utf8');
      const lines = bufRef.current.split('\n');
      // Keep the last (potentially incomplete) fragment
      bufRef.current = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        let event: SolvitaEvent;
        try {
          event = JSON.parse(trimmed) as SolvitaEvent;
        } catch {
          // Non-JSON line (shouldn't happen with --stream-events) — ignore
          continue;
        }
        handleEvent(event, dispatch);
      }
    });

    proc.on('close', () => {
      // Flush any remaining buffer content
      if (bufRef.current.trim()) {
        try {
          const event = JSON.parse(bufRef.current.trim()) as SolvitaEvent;
          handleEvent(event, dispatch);
        } catch {
          // ignore
        }
        bufRef.current = '';
      }
      dispatch({ type: 'DONE' });
    });

    return () => {
      proc.kill();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}

function handleEvent(event: SolvitaEvent, dispatch: Dispatch<Action>): void {
  switch (event.type) {
    case 'phase_start':
      dispatch({ type: 'PHASE_START', phase: event.phase, label: event.label });
      break;
    case 'phase_done':
      dispatch({ type: 'PHASE_DONE', phase: event.phase, data: event.data });
      break;
    case 'final':
      dispatch({ type: 'FINAL', event });
      break;
    case 'solution_saved':
      dispatch({ type: 'SOLUTION_SAVED', path: event.path });
      break;
    case 'error':
      dispatch({ type: 'ERROR', message: event.message });
      break;
    default:
      break;
  }
}
