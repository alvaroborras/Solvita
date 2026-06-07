# CLI Command Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-solve `Command` tab to the AlgoPilot CLI so users can update session-scoped defaults for `model`, `maxIterations`, `pythonBin`, and `output` using a few slash commands before launching a solve.

**Architecture:** Keep the current pre-solve UI shape and add a fourth tab rather than changing the running-solve screen. Put all command parsing and validation into a pure `commandState` module, reuse the existing path and integer parsing helpers, and plumb `model` through the CLI solve options into the backend process arguments.

**Tech Stack:** TypeScript, Ink, Execa, Node.js built-in test runner, existing `main.py --model/--max-iterations` backend

---

## File Map

- `cli/src/types.ts`
  Extend session/default solve option types with optional `model`.
- `cli/src/solveOptions.ts`
  Reuse existing path resolution and integer validation helpers; keep as the shared CLI normalization layer.
- `cli/src/solveOptions.test.ts`
  Add model-carrying solve-option assertions.
- `cli/src/hooks/solverProcess.ts`
  Pass `--model` to the backend when the session default model is set.
- `cli/src/hooks/solverProcess.test.ts`
  Add one process-argument-level regression around model propagation.
- `cli/src/commandState.ts` (new)
  Pure slash-command parser/executor for session-scoped defaults.
- `cli/src/commandState.test.ts` (new)
  Covers all supported commands, reset/show, validation failures, and path resolution for `/python` and `/output`.
- `cli/src/components/CommandMode.tsx` (new)
  One-line command entry UI, current configuration summary, latest feedback.
- `cli/src/components/InputMode.tsx`
  Add the `Command` tab and render `CommandMode`.
- `cli/src/App.tsx`
  Own the current session defaults, pass them to `InputMode`, and use them for future solves.
- `cli/README.md`
  Document the new `Command` tab and the built-in commands.

## Session Defaults Model

The current CLI session will carry one in-memory defaults object:

- `projectRoot`
- `output`
- `maxIterations`
- `pythonBin`
- `model?`

These defaults are:

- initialized when the CLI starts
- mutated only through the new `Command` tab
- applied to future solves started from picker/path/paste mode
- never written to disk

---

### Task 1: Add Model Plumbing to Solve Options and Backend Spawn

**Files:**
- Modify: `cli/src/types.ts`
- Modify: `cli/src/solveOptions.test.ts`
- Modify: `cli/src/hooks/solverProcess.ts`
- Modify: `cli/src/hooks/solverProcess.test.ts`

- [ ] **Step 1: Write the failing tests for model-aware solve options**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSolveOptionsFromInput, type InteractiveSolveDefaults } from './solveOptions.ts';

test('buildSolveOptionsFromInput carries the session model into the next solve', () => {
  const defaults: InteractiveSolveDefaults = {
    projectRoot: '/repo',
    output: '/repo/solution.cpp',
    maxIterations: 5,
    pythonBin: '/usr/bin/python3',
    model: 'gpt-4.1-mini',
  };

  const options = buildSolveOptionsFromInput(defaults, '/tmp/problem.json');

  assert.equal(options.model, 'gpt-4.1-mini');
});
```

```ts
import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSolverArgs } from './solverProcess.ts';
import type { SolveOptions } from '../types.ts';

function makeOptions(overrides: Partial<SolveOptions> = {}): SolveOptions {
  return {
    projectRoot: '/repo',
    inputFile: '/repo/problem.json',
    output: '/repo/solution.cpp',
    maxIterations: 5,
    pythonBin: 'python3',
    ...overrides,
  };
}

test('buildSolverArgs appends --model when a session model is set', () => {
  const args = buildSolverArgs(makeOptions({ model: 'gpt-4.1-mini' }));
  assert.deepEqual(args, [
    'main.py',
    '--input', '/repo/problem.json',
    '--output', '/repo/solution.cpp',
    '--max-iterations', '5',
    '--model', 'gpt-4.1-mini',
    '--stream-events',
  ]);
});

test('buildSolverArgs omits --model when unset', () => {
  const args = buildSolverArgs(makeOptions());
  assert.deepEqual(args, [
    'main.py',
    '--input', '/repo/problem.json',
    '--output', '/repo/solution.cpp',
    '--max-iterations', '5',
    '--stream-events',
  ]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/solveOptions.test.ts src/hooks/solverProcess.test.ts
```

Expected:
- FAIL because `SolveOptions`/`InteractiveSolveDefaults` do not yet include `model`
- FAIL because `buildSolverArgs` does not exist yet

- [ ] **Step 3: Extend `cli/src/types.ts` and `solverProcess.ts`**

```ts
// cli/src/types.ts
export interface SolveOptions {
  projectRoot: string;
  inputFile: string;
  cleanupInputFileOnExit?: boolean;
  output: string;
  maxIterations: number;
  pythonBin: string;
  model?: string;
}

export type InteractiveSolveDefaults = Omit<SolveOptions, 'inputFile' | 'cleanupInputFileOnExit'>;
```

```ts
// cli/src/hooks/solverProcess.ts
export function buildSolverArgs(options: SolveOptions): string[] {
  const args = [
    'main.py',
    '--input',
    options.inputFile,
    '--output',
    options.output,
    '--max-iterations',
    String(options.maxIterations),
  ];

  if (options.model && options.model.trim()) {
    args.push('--model', options.model.trim());
  }

  args.push('--stream-events');
  return args;
}

function spawnSolverProcess(options: SolveOptions): ResultPromise {
  return execa(options.pythonBin, buildSolverArgs(options), {
    cwd: options.projectRoot,
    stdout: 'pipe',
    stderr: 'pipe',
    reject: false,
  });
}
```

- [ ] **Step 4: Re-run the targeted tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/solveOptions.test.ts src/hooks/solverProcess.test.ts
npm run build
```

Expected:
- tests PASS
- build PASS

- [ ] **Step 5: Commit Task 1**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/src/types.ts cli/src/solveOptions.test.ts cli/src/hooks/solverProcess.ts cli/src/hooks/solverProcess.test.ts
git commit -m "feat: plumb cli session model into solve options"
```

---

### Task 2: Add Pure Command Parsing and Session-Defaults Execution

**Files:**
- Create: `cli/src/commandState.ts`
- Create: `cli/src/commandState.test.ts`
- Modify: `cli/src/solveOptions.ts`

- [ ] **Step 1: Write the failing command-state tests**

```ts
import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';

import {
  executeCommand,
  formatCommandSummaryLines,
  type CommandFeedback,
} from './commandState.ts';
import type { InteractiveSolveDefaults } from './types.ts';

const initialDefaults: InteractiveSolveDefaults = {
  projectRoot: '/repo',
  output: '/repo/solution.cpp',
  maxIterations: 5,
  pythonBin: '/usr/bin/python3',
  model: undefined,
};

test('model command updates the session model', () => {
  const result = executeCommand({
    rawInput: '/model gpt-4.1-mini',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.equal(result.nextDefaults.model, 'gpt-4.1-mini');
  assert.equal(result.feedback.kind, 'success');
});

test('max-iterations command updates the session iteration cap', () => {
  const result = executeCommand({
    rawInput: '/max-iterations 8',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.equal(result.nextDefaults.maxIterations, 8);
});

test('python command resolves relative paths from cwd', () => {
  const result = executeCommand({
    rawInput: '/python ./venv/bin/python',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.equal(result.nextDefaults.pythonBin, path.resolve('/work', './venv/bin/python'));
});

test('output command resolves relative paths from cwd', () => {
  const result = executeCommand({
    rawInput: '/output ./my_solution.cpp',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.equal(result.nextDefaults.output, path.resolve('/work', './my_solution.cpp'));
});

test('show command preserves defaults and returns informational feedback', () => {
  const result = executeCommand({
    rawInput: '/show',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.deepEqual(result.nextDefaults, initialDefaults);
  assert.equal(result.feedback.kind, 'info');
});

test('reset restores the original defaults', () => {
  const currentDefaults = { ...initialDefaults, model: 'gpt-4.1-mini', maxIterations: 9 };
  const result = executeCommand({
    rawInput: '/reset',
    currentDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.deepEqual(result.nextDefaults, initialDefaults);
});

test('invalid commands do not mutate defaults', () => {
  const result = executeCommand({
    rawInput: '/temperature 0.2',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.deepEqual(result.nextDefaults, initialDefaults);
  assert.equal(result.feedback.kind, 'error');
});

test('commands must start with slash', () => {
  const result = executeCommand({
    rawInput: 'model gpt-4.1-mini',
    currentDefaults: initialDefaults,
    initialDefaults,
    cwd: '/work',
  });

  assert.equal(result.feedback.message, 'commands must start with /');
});

test('summary lines reflect the current defaults', () => {
  const lines = formatCommandSummaryLines({
    ...initialDefaults,
    model: 'gpt-4.1-mini',
    maxIterations: 8,
  });

  assert.deepEqual(lines, [
    'model: gpt-4.1-mini',
    'max_iterations: 8',
    'python: /usr/bin/python3',
    'output: /repo/solution.cpp',
  ]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/commandState.test.ts
```

Expected:
- FAIL because `commandState.ts` does not exist yet

- [ ] **Step 3: Implement the pure command engine**

```ts
// cli/src/commandState.ts
import { parseMaxIterations, resolveCliPath } from './solveOptions.js';
import type { InteractiveSolveDefaults } from './types.js';

export interface CommandFeedback {
  kind: 'success' | 'error' | 'info';
  message: string;
}

export interface CommandExecutionResult {
  nextDefaults: InteractiveSolveDefaults;
  feedback: CommandFeedback;
}

export function formatCommandSummaryLines(defaults: InteractiveSolveDefaults): string[] {
  return [
    `model: ${defaults.model || '(unset)'}`,
    `max_iterations: ${defaults.maxIterations}`,
    `python: ${defaults.pythonBin}`,
    `output: ${defaults.output}`,
  ];
}

function usage(command: string, syntax: string): CommandExecutionResult['feedback'] {
  return { kind: 'error', message: `usage: ${command} ${syntax}` };
}

export function executeCommand({
  rawInput,
  currentDefaults,
  initialDefaults,
  cwd,
}: {
  rawInput: string;
  currentDefaults: InteractiveSolveDefaults;
  initialDefaults: InteractiveSolveDefaults;
  cwd: string;
}): CommandExecutionResult {
  const trimmed = rawInput.trim();
  if (!trimmed.startsWith('/')) {
    return {
      nextDefaults: currentDefaults,
      feedback: { kind: 'error', message: 'commands must start with /' },
    };
  }

  const [command, ...rest] = trimmed.split(/\s+/);
  const value = rest.join(' ').trim();

  switch (command) {
    case '/model':
      if (!value) return { nextDefaults: currentDefaults, feedback: usage('/model', '<name>') };
      return {
        nextDefaults: { ...currentDefaults, model: value },
        feedback: { kind: 'success', message: `model updated: ${value}` },
      };
    case '/max-iterations':
      if (!value) return { nextDefaults: currentDefaults, feedback: usage('/max-iterations', '<positive-int>') };
      return {
        nextDefaults: { ...currentDefaults, maxIterations: parseMaxIterations(value) },
        feedback: { kind: 'success', message: `max iterations updated: ${parseMaxIterations(value)}` },
      };
    case '/python':
      if (!value) return { nextDefaults: currentDefaults, feedback: usage('/python', '<path-or-binary>') };
      return {
        nextDefaults: { ...currentDefaults, pythonBin: resolveCliPath(value, cwd) },
        feedback: { kind: 'success', message: `python updated: ${resolveCliPath(value, cwd)}` },
      };
    case '/output':
      if (!value) return { nextDefaults: currentDefaults, feedback: usage('/output', '<path>') };
      return {
        nextDefaults: { ...currentDefaults, output: resolveCliPath(value, cwd) },
        feedback: { kind: 'success', message: `output updated: ${resolveCliPath(value, cwd)}` },
      };
    case '/show':
      return {
        nextDefaults: currentDefaults,
        feedback: { kind: 'info', message: 'current settings shown below' },
      };
    case '/reset':
      return {
        nextDefaults: { ...initialDefaults },
        feedback: { kind: 'success', message: 'session defaults reset' },
      };
    default:
      return {
        nextDefaults: currentDefaults,
        feedback: { kind: 'error', message: `unknown command: ${command}` },
      };
  }
}
```

- [ ] **Step 4: Re-run the command-state tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/commandState.test.ts
npm run build
```

Expected:
- tests PASS
- build PASS

- [ ] **Step 5: Commit Task 2**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/src/commandState.ts cli/src/commandState.test.ts cli/src/solveOptions.ts
git commit -m "feat: add cli command execution state"
```

---

### Task 3: Add `Command` Tab UI and Session-Defaults Integration

**Files:**
- Create: `cli/src/components/CommandMode.tsx`
- Modify: `cli/src/components/InputMode.tsx`
- Modify: `cli/src/App.tsx`
- Modify: `cli/src/types.ts`

- [ ] **Step 1: Extend the pure tests with one reset/show regression before wiring UI**

```ts
test('reset restores a previously customized output and python path', () => {
  const customized = {
    ...initialDefaults,
    output: '/work/my_solution.cpp',
    pythonBin: '/work/.venv/bin/python',
  };

  const result = executeCommand({
    rawInput: '/reset',
    currentDefaults: customized,
    initialDefaults,
    cwd: '/work',
  });

  assert.deepEqual(result.nextDefaults, initialDefaults);
});
```

- [ ] **Step 2: Run the test to keep the command core green before UI wiring**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/commandState.test.ts
```

Expected:
- PASS

- [ ] **Step 3: Add the new `CommandMode` UI component**

```tsx
// cli/src/components/CommandMode.tsx
import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';

import { executeCommand, formatCommandSummaryLines } from '../commandState.js';
import { PALETTE } from '../theme.js';
import type { InteractiveSolveDefaults } from '../types.js';

interface CommandModeProps {
  cwd: string;
  currentDefaults: InteractiveSolveDefaults;
  initialDefaults: InteractiveSolveDefaults;
  onDefaultsChange: (next: InteractiveSolveDefaults) => void;
}

export function CommandMode({
  cwd,
  currentDefaults,
  initialDefaults,
  onDefaultsChange,
}: CommandModeProps) {
  const [commandText, setCommandText] = useState('');
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error' | 'info'; message: string } | null>(null);

  useInput((input, key) => {
    if (key.return) {
      if (!commandText.trim()) return;
      const result = executeCommand({
        rawInput: commandText,
        currentDefaults,
        initialDefaults,
        cwd,
      });
      onDefaultsChange(result.nextDefaults);
      setFeedback(result.feedback);
      setCommandText('');
      return;
    }

    if (key.backspace || key.delete) {
      setCommandText((value) => value.slice(0, -1));
      return;
    }

    if (input && !key.ctrl && !key.meta) {
      setCommandText((value) => value + input);
    }
  });

  const summaryLines = formatCommandSummaryLines(currentDefaults);

  return (
    <Box flexDirection="column">
      <Text color={PALETTE.meta}>{'  Commands: /model /max-iterations /python /output /show /reset'}</Text>
      <Box borderStyle="round" borderColor={PALETTE.defender} paddingX={1} marginTop={1}>
        <Text color={PALETTE.text}>{commandText || ' '}</Text>
        <Text color={PALETTE.defender}>{'█'}</Text>
      </Box>
      {feedback && (
        <Text color={feedback.kind === 'error' ? PALETTE.attacker : PALETTE.meta}>
          {`  ${feedback.message}`}
        </Text>
      )}
      <Box flexDirection="column" marginTop={1}>
        <Text color={PALETTE.meta}>{'  Current session settings:'}</Text>
        {summaryLines.map((line) => (
          <Text key={line} color={PALETTE.text}>{`  ${line}`}</Text>
        ))}
      </Box>
    </Box>
  );
}
```

- [ ] **Step 4: Integrate the new tab into `InputMode.tsx` and session defaults into `App.tsx`**

```tsx
// cli/src/components/InputMode.tsx
import { CommandMode } from './CommandMode.js';
import type { InteractiveSolveDefaults } from '../types.js';

type SubMode = 'pick' | 'path' | 'paste' | 'command';

interface InputModeProps {
  projectRoot: string;
  cwd: string;
  currentDefaults: InteractiveSolveDefaults;
  initialDefaults: InteractiveSolveDefaults;
  onDefaultsChange: (next: InteractiveSolveDefaults) => void;
  onSubmit: (inputFile: string, description?: string) => void;
}

const tabLabels: Record<SubMode, string> = {
  pick: ' Select problem file ',
  path: ' Enter file path     ',
  paste: ' Paste description   ',
  command: ' Command             ',
};

// when subMode === 'command'
<CommandMode
  cwd={cwd}
  currentDefaults={currentDefaults}
  initialDefaults={initialDefaults}
  onDefaultsChange={onDefaultsChange}
/>;
```

```tsx
// cli/src/App.tsx
const initialSessionDefaults: InteractiveSolveDefaults = {
  projectRoot: root,
  output: resolveCliPath('solution.cpp', cwd),
  maxIterations: 5,
  pythonBin: detectPythonBin(),
  model: process.env.ALGOPILOT_MODEL || undefined,
};

const [sessionDefaults, setSessionDefaults] = useState<InteractiveSolveDefaults>(initialSessionDefaults);

const handleInputSubmit = useCallback(
  (inputFile: string, description?: string) => {
    const isPastedDescription = !inputFile && Boolean(description);
    let resolvedFile = inputFile;

    if (isPastedDescription && description) {
      resolvedFile = createTempInputFile(description);
    }

    if (!resolvedFile) {
      return;
    }

    const nextOptions = buildSolveOptionsFromInput(
      sessionDefaults,
      resolveCliPath(resolvedFile, cwd),
    );

    setSolveOptions(
      isPastedDescription
        ? markTempInputSolveOptionsForCleanup(nextOptions)
        : nextOptions,
    );
  },
  [cwd, sessionDefaults],
);

<InputMode
  projectRoot={root}
  cwd={cwd}
  currentDefaults={sessionDefaults}
  initialDefaults={initialSessionDefaults}
  onDefaultsChange={setSessionDefaults}
  onSubmit={handleInputSubmit}
/>;
```

- [ ] **Step 5: Re-run the test/build suite**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test
npm run build
node bin/algopilot.js --help
```

Expected:
- all current tests PASS
- build PASS
- help command still PASS

- [ ] **Step 6: Commit Task 3**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/src/components/CommandMode.tsx cli/src/components/InputMode.tsx cli/src/App.tsx cli/src/types.ts cli/src/commandState.ts cli/src/commandState.test.ts
git commit -m "feat: add pre-solve cli command mode"
```

---

### Task 4: Make Solve View Use Command-Updated Defaults and Update Runtime Text

**Files:**
- Modify: `cli/src/App.tsx`
- Modify: `cli/src/components/Header.tsx` (or keep in `App.tsx` if model label stays there)
- Modify: `cli/src/hooks/solverProcess.test.ts`

- [ ] **Step 1: Write the failing model-propagation regression**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSolverArgs } from './solverProcess.ts';

test('buildSolverArgs uses the command-updated model for backend execution', () => {
  const args = buildSolverArgs({
    projectRoot: '/repo',
    inputFile: '/repo/problem.json',
    output: '/repo/solution.cpp',
    maxIterations: 5,
    pythonBin: 'python3',
    model: 'gpt-4.1-mini',
  });

  assert.ok(args.includes('--model'));
  assert.ok(args.includes('gpt-4.1-mini'));
});
```

- [ ] **Step 2: Run the targeted regression to verify it passes after the Task 1 plumbing**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/hooks/solverProcess.test.ts
```

Expected:
- PASS once Task 1 is correctly implemented

- [ ] **Step 3: Display the current solve model label from session defaults**

```tsx
// cli/src/App.tsx
<AlgoPilotHeader
  problemId={...}
  modelLabel={options.model ?? process.env.ALGOPILOT_MODEL || undefined}
  startedAt={state.startedAt}
  tokens={tokens}
  tokenSamples={state.tokenSamples}
  cost={null}
  width={width}
  platformWarning={isWindows}
/>
```

- [ ] **Step 4: Re-run the full CLI verification**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test
npm run build
node bin/algopilot.js --help

cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./run_algopilot.sh --help
```

Expected:
- CLI tests PASS
- CLI build PASS
- direct help PASS
- wrapper help PASS

- [ ] **Step 5: Commit Task 4**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/src/App.tsx cli/src/hooks/solverProcess.test.ts
git commit -m "feat: apply cli command defaults to solves"
```

---

### Task 5: Update CLI Documentation for Command Mode

**Files:**
- Modify: `cli/README.md`

- [ ] **Step 1: Update the README examples and command documentation**

```md
## Interactive mode

The pre-solve UI has four tabs:
- Select problem file
- Enter file path
- Paste description
- Command

### Command mode

The `Command` tab lets you change session-scoped defaults before starting a solve.

Supported commands:
- `/model <name>`
- `/max-iterations <positive-int>`
- `/python <path-or-binary>`
- `/output <path>`
- `/show`
- `/reset`

These commands affect only the current CLI session.
They do not modify repository config files or environment variables.
```

- [ ] **Step 2: Run final docs verification**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test
npm run build
node bin/algopilot.js --help
```

Expected:
- tests PASS
- build PASS
- help PASS

- [ ] **Step 3: Commit Task 5**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/README.md
git commit -m "docs: document cli command mode"
```
