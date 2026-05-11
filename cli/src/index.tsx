#!/usr/bin/env node
/**
 * Solvita CLI entry point.
 *
 * Usage:
 *   solvita                                # interactive mode
 *   solvita solve <problem.json>           # solve a specific file
 *   solvita solve <problem.json> [options] # with options
 */

import React from 'react';
import { render } from 'ink';
import { Command } from 'commander';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

import { App } from './App.js';
import type { SolveOptions } from './types.js';

// ─── Project root resolution ──────────────────────────────────────────────────

function getProjectRoot(): string {
  // index.tsx compiles to dist/index.js
  //  dist/index.js  →  dist/  →  cli/  →  solvita-final/
  const __filename = fileURLToPath(import.meta.url);
  const distDir = path.dirname(__filename);
  const cliDir = path.dirname(distDir);
  return path.dirname(cliDir);
}

function detectPythonBin(): string {
  return os.platform() === 'win32' ? 'python' : 'python3';
}

// ─── Launch helpers ───────────────────────────────────────────────────────────

function launchInteractive(projectRoot: string) {
  render(<App initialOptions={null} projectRoot={projectRoot} />, { exitOnCtrlC: true });
}

function launchSolve(opts: SolveOptions) {
  render(<App initialOptions={opts} projectRoot={opts.projectRoot} />, { exitOnCtrlC: true });
}

// ─── CLI setup ────────────────────────────────────────────────────────────────

const projectRoot = getProjectRoot();

const program = new Command('solvita')
  .description('Solvita — Intelligent Competitive Programming Agent')
  .version('0.1.0')
  .helpOption('-h, --help', 'Show help')
  // No args → interactive mode
  .action(() => {
    launchInteractive(projectRoot);
  });

// `solvita solve [file]` subcommand
program
  .command('solve [file]')
  .description('Solve a competitive programming problem')
  .option('-o, --output <path>', 'Output .cpp file path', 'solution.cpp')
  .option('-n, --max-iterations <n>', 'Max LLM refinement iterations', '5')
  .option(
    '-p, --python <bin>',
    'Python executable (default: python on Windows, python3 on Linux/mac)',
  )
  .action((file: string | undefined, opts: Record<string, string>) => {
    const pythonBin = opts['python'] ?? detectPythonBin();
    const maxIterations = parseInt(opts['maxIterations'] ?? '5', 10);
    const outputRaw = opts['output'] ?? 'solution.cpp';
    const outputPath = path.isAbsolute(outputRaw)
      ? outputRaw
      : path.join(projectRoot, outputRaw);

    if (file) {
      const inputFile = path.isAbsolute(file) ? file : path.resolve(process.cwd(), file);
      launchSolve({ projectRoot, inputFile, output: outputPath, maxIterations, pythonBin });
    } else {
      // `solvita solve` with no file → interactive
      launchInteractive(projectRoot);
    }
  });

program.parse(process.argv);
