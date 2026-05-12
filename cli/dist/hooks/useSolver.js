import { useEffect, useReducer, useRef } from 'react';
import { execa } from 'execa';
// ─── Phase routing ────────────────────────────────────────────────────────────
// Map raw event.phase strings to one of three buckets; everything not listed is
// dropped silently (kept in `phases` for legacy compat).
const ARENA_KEYS = new Set([
    'abstract_phase',
    'testgen_phase',
    'solver_skill_plan',
]);
const DEFENDER_KEYS = new Set(['codegen_phase']);
const ATTACKER_KEYS = new Set(['hacker_phase']);
function makeArenaUpdate(prev, key, label, status, data) {
    const existing = prev.find((a) => a.key === key);
    const merged = existing
        ? { ...existing, status }
        : { key, label, status };
    if (status === 'done' && data) {
        if (key === 'abstract_phase') {
            const d = data;
            merged.tags = d.tags ?? [];
            merged.confidence = d.confidence;
        }
        else if (key === 'testgen_phase') {
            const d = data;
            merged.testCount = d.test_count;
        }
        else if (key === 'solver_skill_plan') {
            const d = data;
            merged.algorithm = d.algorithm ?? '';
        }
    }
    return existing
        ? prev.map((a) => (a.key === key ? merged : a))
        : [...prev, merged];
}
function reducer(state, action) {
    switch (action.type) {
        case 'SOLVE_START':
            return {
                ...state,
                problemId: action.problemId,
                maxIterations: action.maxIterations,
                startedAt: Date.now(),
            };
        case 'PHASE_START': {
            const phase = action.phase;
            if (ARENA_KEYS.has(phase)) {
                return {
                    ...state,
                    arena: makeArenaUpdate(state.arena, phase, action.label, 'running'),
                    phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
                };
            }
            // Defender: each new codegen_phase opens a fresh iteration row whose
            // iteration number is filled in on phase_done. The node fires multiple
            // phase_starts inside the same iter — ignore re-entries.
            if (DEFENDER_KEYS.has(phase)) {
                const lastDefender = state.defender[state.defender.length - 1];
                if (!lastDefender) {
                    return {
                        ...state,
                        defender: [{ iteration: 0, status: 'running' }],
                        phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
                    };
                }
                if (lastDefender.status === 'done') {
                    return {
                        ...state,
                        defender: [
                            ...state.defender,
                            { iteration: -1, status: 'running', patched: state.defender.length > 0 },
                        ],
                        phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
                    };
                }
                return state;
            }
            if (ATTACKER_KEYS.has(phase)) {
                const lastAttacker = state.attacker[state.attacker.length - 1];
                if (!lastAttacker) {
                    return {
                        ...state,
                        attacker: [{ round: 1, status: 'running' }],
                        phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
                    };
                }
                if (lastAttacker.status === 'done') {
                    return {
                        ...state,
                        attacker: [
                            ...state.attacker,
                            { round: lastAttacker.round + 1, status: 'running' },
                        ],
                        phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
                    };
                }
                return state;
            }
            return {
                ...state,
                phases: appendPhaseLegacy(state.phases, phase, action.label, 'running'),
            };
        }
        case 'PHASE_DONE': {
            const phase = action.phase;
            const data = action.data;
            if (ARENA_KEYS.has(phase)) {
                return {
                    ...state,
                    arena: makeArenaUpdate(state.arena, phase, action.label, 'done', data),
                    phases: markPhaseLegacy(state.phases, phase, 'done'),
                };
            }
            if (DEFENDER_KEYS.has(phase)) {
                const d = data;
                const last = state.defender[state.defender.length - 1];
                const nextRow = {
                    iteration: d.iteration,
                    status: 'done',
                    compileSuccess: d.compile_success,
                    passed: d.passed,
                    total: d.total,
                    passRate: d.pass_rate,
                    patched: last?.patched ?? false,
                };
                const updated = last
                    ? state.defender.slice(0, -1).concat(nextRow)
                    : [nextRow];
                return {
                    ...state,
                    defender: updated,
                    phases: markPhaseLegacy(state.phases, phase, 'done'),
                };
            }
            if (ATTACKER_KEYS.has(phase)) {
                const d = data;
                const last = state.attacker[state.attacker.length - 1];
                const round = d.hack_round ?? last?.round ?? 1;
                const landed = d.hack_passed === false;
                const nextRow = { round, status: 'done', landed };
                const updatedAttacker = last
                    ? state.attacker.slice(0, -1).concat(nextRow)
                    : [nextRow];
                let strikes = state.strikes;
                if (landed) {
                    const lastDef = [...state.defender].reverse().find((dd) => dd.status === 'done');
                    const strike = {
                        round,
                        defenderIter: lastDef?.iteration ?? 0,
                        failureType: d.failure_type,
                        failingInputHead: d.failing_input_head,
                        expectedHead: d.expected_head,
                        actualHead: d.actual_head,
                        details: d.details,
                    };
                    strikes = [...strikes, strike];
                }
                return {
                    ...state,
                    attacker: updatedAttacker,
                    strikes,
                    phases: markPhaseLegacy(state.phases, phase, 'done'),
                };
            }
            return {
                ...state,
                phases: markPhaseLegacy(state.phases, phase, 'done'),
            };
        }
        case 'FINAL':
            return {
                ...state,
                finalEvent: action.event,
                tokenSamples: [
                    ...state.tokenSamples,
                    (action.event.prompt_tokens ?? 0) + (action.event.completion_tokens ?? 0),
                ],
            };
        case 'TOKEN_SAMPLE':
            // Cap retained samples to avoid unbounded growth on long runs;
            // sparkline only renders the trailing window anyway.
            return {
                ...state,
                tokenSamples: [...state.tokenSamples, action.total].slice(-256),
            };
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
// ─── Legacy flat-list helpers ───────────────────────────────────────────────
function appendPhaseLegacy(prev, key, label, status) {
    const existing = prev.find((p) => p.key === key);
    if (existing) {
        return prev.map((p) => (p.key === key ? { ...p, status, detail: '' } : p));
    }
    return [...prev, { key, label, status, detail: '' }];
}
function markPhaseLegacy(prev, key, status) {
    return prev.map((p) => (p.key === key ? { ...p, status } : p));
}
// ─── Initial state ──────────────────────────────────────────────────────────
const INITIAL_STATE = {
    phases: [],
    arena: [],
    defender: [],
    attacker: [],
    strikes: [],
    finalEvent: null,
    solutionPath: null,
    errorMessage: null,
    running: true,
    problemId: null,
    maxIterations: null,
    startedAt: Date.now(),
    tokenSamples: [],
};
// ─── Hook ────────────────────────────────────────────────────────────────────
export function useSolver(options) {
    const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
    const procRef = useRef(null);
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
            stdout: 'pipe',
            stderr: 'inherit',
            reject: false,
        });
        procRef.current = proc;
        proc.stdout?.on('data', (chunk) => {
            bufRef.current += chunk.toString('utf8');
            const lines = bufRef.current.split('\n');
            bufRef.current = lines.pop() ?? '';
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed)
                    continue;
                let event;
                try {
                    event = JSON.parse(trimmed);
                }
                catch {
                    continue;
                }
                handleEvent(event, dispatch);
            }
        });
        proc.on('close', () => {
            if (bufRef.current.trim()) {
                try {
                    const event = JSON.parse(bufRef.current.trim());
                    handleEvent(event, dispatch);
                }
                catch {
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
function handleEvent(event, dispatch) {
    switch (event.type) {
        case 'solve_start':
            dispatch({
                type: 'SOLVE_START',
                problemId: event.problem_id,
                maxIterations: event.max_iterations,
            });
            break;
        case 'phase_start':
            dispatch({ type: 'PHASE_START', phase: event.phase, label: event.label });
            break;
        case 'phase_done':
            dispatch({
                type: 'PHASE_DONE',
                phase: event.phase,
                label: event.label,
                data: event.data,
            });
            break;
        case 'final':
            dispatch({ type: 'FINAL', event });
            break;
        case 'solution_saved':
            dispatch({ type: 'SOLUTION_SAVED', path: event.path });
            break;
        case 'token_sample':
            dispatch({
                type: 'TOKEN_SAMPLE',
                total: event.total,
                prompt: event.prompt_tokens,
                completion: event.completion_tokens,
            });
            break;
        case 'error':
            dispatch({ type: 'ERROR', message: event.message });
            break;
        default:
            break;
    }
}
//# sourceMappingURL=useSolver.js.map