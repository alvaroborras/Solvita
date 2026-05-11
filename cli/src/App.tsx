/**
 * Root Ink application component.
 *
 * Renders one of two modes:
 *  - "input"  — interactive problem selection / paste (InputMode)
 *  - "solve"  — real-time solve progress (PhaseRow list + Summary)
 */
import React, { useState, useCallback, useEffect } from 'react';
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
import type { SolveOptions } from './types.js';

// ─── Project root resolution ──────────────────────────────────────────────────

export function getProjectRoot(): string {
  // This file compiles to dist/App.js
  //  dist/App.js  →  dist/  →  cli/  →  solvita-final/
  const __filename = fileURLToPath(import.meta.url);
  const distDir = path.dirname(__filename);
  const cliDir = path.dirname(distDir);
  return path.dirname(cliDir);
}

export function detectPythonBin(): string {
  return os.platform() === 'win32' ? 'python' : 'python3';
}

// ─── Types ───────────────────────────────────────────────────────────────────

interface AppProps {
  /**
   * When non-null, skip interactive input and go straight to solving.
   * Set by `solvita solve <file>` subcommand.
   */
  initialOptions: SolveOptions | null;
  /** Explicit project root override (passed from index.tsx which resolves it). */
  projectRoot?: string;
}

// ─── Solve view (shows progress) ─────────────────────────────────────────────

function SolveView({ options }: { options: SolveOptions }) {
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

  return (
    <Box flexDirection="column">
      <Header subtitle={problemLabel} platformWarning={isWindows} />

      <Box flexDirection="column">
        {state.phases.map((phase) => (
          <PhaseRow
            key={phase.key}
            label={phase.label}
            status={phase.status}
            detail={phase.detail}
          />
        ))}
      </Box>

      {state.phases.length === 0 && state.running && (
        <Box paddingX={2}>
          <Text color="gray" dimColor>
            {'  Initialising workflow…'}
          </Text>
        </Box>
      )}

      {state.errorMessage && (
        <Box marginTop={1} paddingX={2}>
          <Text color="red">{'  ✖ Error: '}</Text>
          <Text color="red">{state.errorMessage}</Text>
        </Box>
      )}

      {!state.running && state.finalEvent && (
        <Summary event={state.finalEvent} solutionPath={state.solutionPath} />
      )}

      {!state.running && !state.finalEvent && !state.errorMessage && (
        <Box marginTop={1} paddingX={2}>
          <Text color="yellow">{'  Process exited without a final event.'}</Text>
        </Box>
      )}
    </Box>
  );
}

// ─── Root app ─────────────────────────────────────────────────────────────────

export function App({ initialOptions, projectRoot: rootOverride }: AppProps) {
  const root = rootOverride ?? getProjectRoot();
  const [solveOptions, setSolveOptions] = useState<SolveOptions | null>(initialOptions);

  const handleInputSubmit = useCallback(
    (inputFile: string, description?: string) => {
      let resolvedFile = inputFile;

      if (!inputFile && description) {
        const tmp = path.join(tmpdir(), `solvita_input_${Date.now()}.json`);
        writeFileSync(
          tmp,
          JSON.stringify({
            description,
            time_limit: 2000,
            space_limit: 256,
            public_tests: [],
          }),
          'utf8',
        );
        resolvedFile = tmp;
      }

      if (!resolvedFile) return;

      setSolveOptions({
        projectRoot: root,
        inputFile: resolvedFile,
        output: path.join(root, 'solution.cpp'),
        maxIterations: 5,
        pythonBin: detectPythonBin(),
      });
    },
    [root],
  );

  if (solveOptions) {
    return <SolveView options={solveOptions} />;
  }

  return (
    <Box flexDirection="column">
      <Header />
      <InputMode projectRoot={root} onSubmit={handleInputSubmit} />
    </Box>
  );
}
