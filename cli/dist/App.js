import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * Root Ink application component.
 *
 * Renders one of two modes:
 *  - "input"  — interactive problem selection / paste (InputMode)
 *  - "solve"  — real-time solve progress (PhaseRow list + Summary)
 */
import { useState, useCallback, useEffect } from 'react';
import { Box, Text, useApp } from 'ink';
import os from 'os';
import path from 'path';
import { writeFileSync } from 'fs';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';
import { Header } from './components/Header.js';
import { PhaseRow } from './components/PhaseRow.js';
import { InputMode } from './components/InputMode.js';
import { Summary } from './components/Summary.js';
import { useSolver } from './hooks/useSolver.js';
// ─── Project root resolution ──────────────────────────────────────────────────
export function getProjectRoot() {
    // This file compiles to dist/App.js
    //  dist/App.js  →  dist/  →  cli/  →  solvita-final/
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
    const state = useSolver(options);
    useEffect(() => {
        if (!state.running) {
            const t = setTimeout(() => exit(), 150);
            return () => clearTimeout(t);
        }
    }, [state.running, exit]);
    const problemLabel = path.basename(options.inputFile, '.json');
    const isWindows = os.platform() === 'win32';
    return (_jsxs(Box, { flexDirection: "column", children: [_jsx(Header, { subtitle: problemLabel, platformWarning: isWindows }), _jsx(Box, { flexDirection: "column", children: state.phases.map((phase) => (_jsx(PhaseRow, { label: phase.label, status: phase.status, detail: phase.detail }, phase.key))) }), state.phases.length === 0 && state.running && (_jsx(Box, { paddingX: 2, children: _jsx(Text, { color: "gray", dimColor: true, children: '  Initialising workflow…' }) })), state.errorMessage && (_jsxs(Box, { marginTop: 1, paddingX: 2, children: [_jsx(Text, { color: "red", children: '  ✖ Error: ' }), _jsx(Text, { color: "red", children: state.errorMessage })] })), !state.running && state.finalEvent && (_jsx(Summary, { event: state.finalEvent, solutionPath: state.solutionPath })), !state.running && !state.finalEvent && !state.errorMessage && (_jsx(Box, { marginTop: 1, paddingX: 2, children: _jsx(Text, { color: "yellow", children: '  Process exited without a final event.' }) }))] }));
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
    return (_jsxs(Box, { flexDirection: "column", children: [_jsx(Header, {}), _jsx(InputMode, { projectRoot: root, onSubmit: handleInputSubmit })] }));
}
//# sourceMappingURL=App.js.map