import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * Root Ink application — Adversarial Telemetry layout.
 *
 * Three vertical sections:
 *   ┌────────────────────────────────┐
 *   │ Header (title · meta · spark)  │
 *   ├────────────────────────────────┤
 *   │ ARENA  (abstract / testgen / plan)
 *   ├────────────────────────────────┤
 *   │ DUEL   (defender ↔ attacker)   │
 *   ├────────────────────────────────┤
 *   │ VERDICT (big-text on close)    │
 *   └────────────────────────────────┘
 *
 * Renders one of two top-level modes:
 *  - "input"  — interactive problem selection / paste (InputMode)
 *  - "solve"  — real-time solve progress (Header + Arena + Duel + Verdict)
 */
import { useState, useCallback, useEffect } from 'react';
import { Box, Text, useApp, useStdout } from 'ink';
import os from 'os';
import path from 'path';
import { writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';
import { Header } from './components/Header.js';
import { Arena } from './components/Arena.js';
import { Duel } from './components/Duel.js';
import { Verdict } from './components/Verdict.js';
import { InputMode } from './components/InputMode.js';
import { useSolver } from './hooks/useSolver.js';
import { PALETTE, safeWidth } from './theme.js';
// ─── Project root resolution ──────────────────────────────────────────────────
export function getProjectRoot() {
    const __filename = fileURLToPath(import.meta.url);
    const distDir = path.dirname(__filename);
    const cliDir = path.dirname(distDir);
    return path.dirname(cliDir);
}
export function detectPythonBin() {
    return os.platform() === 'win32' ? 'python' : 'python3';
}
// ─── Solve view (shows progress) ─────────────────────────────────────────────
function SolveView({ options }) {
    const { exit } = useApp();
    const { stdout } = useStdout();
    const state = useSolver(options);
    // Use the terminal width minus a 2-cell right-edge guard so rules never
    // wrap; cap at 140 to keep readable line lengths on ultra-wide screens.
    // When piped (no TTY), `stdout.columns` is undefined; honour $COLUMNS
    // as a deliberate override before falling back to safeWidth's default.
    const envCols = Number.parseInt(process.env.COLUMNS ?? '', 10);
    const rawCols = stdout?.columns ?? (Number.isFinite(envCols) ? envCols : undefined);
    const width = Math.min(safeWidth(rawCols), 140);
    useEffect(() => {
        if (!state.running) {
            const t = setTimeout(() => exit(), 2500);
            return () => clearTimeout(t);
        }
    }, [state.running, exit]);
    const isWindows = os.platform() === 'win32';
    const latestSample = state.tokenSamples[state.tokenSamples.length - 1] ?? 0;
    const tokens = ((state.finalEvent?.prompt_tokens ?? 0) +
        (state.finalEvent?.completion_tokens ?? 0)) ||
        latestSample;
    return (_jsxs(Box, { flexDirection: "column", children: [_jsx(Header, { problemId: state.problemId && state.problemId !== 'unknown'
                    ? state.problemId
                    : path.basename(options.inputFile, '.json'), modelLabel: "gpt-5.5", startedAt: state.startedAt, tokens: tokens, tokenSamples: state.tokenSamples, cost: null, width: width, platformWarning: isWindows }), _jsx(Arena, { arena: state.arena, width: width }), _jsx(Duel, { defender: state.defender, attacker: state.attacker, strikes: state.strikes, width: width }), state.errorMessage && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { color: PALETTE.verdictError, children: `  ⚠  ${state.errorMessage}` }) })), !state.running && state.finalEvent && (_jsx(Verdict, { event: state.finalEvent, solutionPath: state.solutionPath, startedAt: state.startedAt, width: width })), !state.running && !state.finalEvent && !state.errorMessage && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { color: PALETTE.attacker, children: '  Process exited without a final event.' }) }))] }));
}
// ─── Root app ─────────────────────────────────────────────────────────────────
export function App({ initialOptions, projectRoot: rootOverride }) {
    const root = rootOverride ?? getProjectRoot();
    const [solveOptions, setSolveOptions] = useState(initialOptions);
    const handleInputSubmit = useCallback((inputFile, description) => {
        let resolvedFile = inputFile;
        if (!inputFile && description) {
            const tmp = path.join(tmpdir(), `solvita_input_${Date.now()}.json`);
            writeFileSync(tmp, JSON.stringify({
                description,
                time_limit: 2000,
                space_limit: 256,
                public_tests: [],
            }), 'utf8');
            resolvedFile = tmp;
        }
        if (!resolvedFile)
            return;
        setSolveOptions({
            projectRoot: root,
            inputFile: resolvedFile,
            output: path.join(root, 'solution.cpp'),
            maxIterations: 5,
            pythonBin: detectPythonBin(),
        });
    }, [root]);
    if (solveOptions) {
        return _jsx(SolveView, { options: solveOptions });
    }
    return (_jsxs(Box, { flexDirection: "column", children: [_jsx(Header, { problemId: null, startedAt: Date.now(), tokens: 0, cost: null, width: 100 }), _jsx(InputMode, { projectRoot: root, onSubmit: handleInputSubmit })] }));
}
//# sourceMappingURL=App.js.map