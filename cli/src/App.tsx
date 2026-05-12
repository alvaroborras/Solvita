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
import React, { useState, useCallback, useEffect } from 'react';
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
import { PALETTE } from './theme.js';
import type { SolveOptions } from './types.js';

// ─── Project root resolution ──────────────────────────────────────────────────

export function getProjectRoot(): string {
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
  initialOptions: SolveOptions | null;
  projectRoot?: string;
}

// ─── Solve view (shows progress) ─────────────────────────────────────────────

function SolveView({ options }: { options: SolveOptions }) {
  const { exit } = useApp();
  const { stdout } = useStdout();
  const state = useSolver(options);

  // Honor terminal width; fall back to 100 if unknown
  const width = Math.max(80, Math.min(stdout?.columns ?? 100, 140));

  useEffect(() => {
    if (!state.running) {
      const t = setTimeout(() => exit(), 2500);
      return () => clearTimeout(t);
    }
  }, [state.running, exit]);

  const isWindows = os.platform() === 'win32';
  const latestSample = state.tokenSamples[state.tokenSamples.length - 1] ?? 0;
  const tokens =
    ((state.finalEvent?.prompt_tokens ?? 0) +
      (state.finalEvent?.completion_tokens ?? 0)) ||
    latestSample;

  return (
    <Box flexDirection="column">
      <Header
        problemId={
          state.problemId && state.problemId !== 'unknown'
            ? state.problemId
            : path.basename(options.inputFile, '.json')
        }
        modelLabel="gpt-5.5"
        startedAt={state.startedAt}
        tokens={tokens}
        tokenSamples={state.tokenSamples}
        cost={null}
        width={width}
        platformWarning={isWindows}
      />

      <Arena arena={state.arena} width={width} />

      <Duel
        defender={state.defender}
        attacker={state.attacker}
        strikes={state.strikes}
        width={width}
      />

      {state.errorMessage && (
        <Box marginTop={1}>
          <Text color={PALETTE.verdictError}>{`  ⚠  ${state.errorMessage}`}</Text>
        </Box>
      )}

      {!state.running && state.finalEvent && (
        <Verdict
          event={state.finalEvent}
          solutionPath={state.solutionPath}
          startedAt={state.startedAt}
          width={width}
        />
      )}

      {!state.running && !state.finalEvent && !state.errorMessage && (
        <Box marginTop={1}>
          <Text color={PALETTE.attacker}>
            {'  Process exited without a final event.'}
          </Text>
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
      <Header
        problemId={null}
        startedAt={Date.now()}
        tokens={0}
        cost={null}
        width={100}
      />
      <InputMode projectRoot={root} onSubmit={handleInputSubmit} />
    </Box>
  );
}
