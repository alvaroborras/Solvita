# Dashboard Algorithm Story Success-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide `AlgorithmStoryCard` whenever a run has completed with any final status other than `success`, while leaving live/in-progress behavior unchanged.

**Architecture:** Keep this as a page-level rendering rule in `App.tsx`. Do not alter artifact extraction or the playback component itself. Add one focused `App`-level regression test that proves a completed non-success run does not render the algorithm story card, while successful and live runs keep existing behavior.

**Tech Stack:** React 18, TypeScript, Testing Library, Vitest

---

## File Map

- `dashboard/frontend/src/App.tsx`
  - Owns page-level orchestration and decides which major cards render.
  - Will gain the final-status gate for `AlgorithmStoryCard`.
- `dashboard/frontend/src/App.test.tsx`
  - Owns integration coverage for dashboard rendering behavior.
  - Will gain the non-success visibility regression test.

## Execution Note

Implement this plan in:

`/ssd-disk/lih/Software-Engineering-work/algorithm-agent`

Do not touch backend files, artifact extraction, or `AlgorithmStoryCard.tsx`.

### Task 1: Add a failing `App`-level regression test

**Files:**
- Modify: `dashboard/frontend/src/App.test.tsx`
- Test: `dashboard/frontend/src/App.test.tsx`

- [ ] **Step 1: Write the failing test**

Add this test to `dashboard/frontend/src/App.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd dashboard/frontend && npx vitest run src/App.test.tsx`

Expected:
- the new test fails because `App.tsx` still renders `AlgorithmStoryCard` after a completed non-success run

- [ ] **Step 3: Commit the red checkpoint only if your workflow explicitly wants it**

```bash
git add dashboard/frontend/src/App.test.tsx
git commit -m "test: lock algorithm story success-only visibility"
```

If your workflow does not want a red-state commit, skip this commit and continue.

### Task 2: Gate `AlgorithmStoryCard` rendering in `App.tsx`

**Files:**
- Modify: `dashboard/frontend/src/App.tsx`
- Modify: `dashboard/frontend/src/App.test.tsx`
- Test: `dashboard/frontend/src/App.test.tsx`

- [ ] **Step 1: Implement the page-level visibility rule**

In `dashboard/frontend/src/App.tsx`, replace the unconditional render:

```tsx
      <AlgorithmStoryCard
        story={displayArtifacts.finalArtifact?.algorithmVisualization || null}
        mode={session.mode}
        revision={displayArtifacts.finalArtifact?.solution.version || 0}
      />
```

with:

```tsx
      {(finalStatus === null || finalStatus === 'success') && (
        <AlgorithmStoryCard
          story={displayArtifacts.finalArtifact?.algorithmVisualization || null}
          mode={session.mode}
          revision={displayArtifacts.finalArtifact?.solution.version || 0}
        />
      )}
```

- [ ] **Step 2: Run the focused test to verify it passes**

Run: `cd dashboard/frontend && npx vitest run src/App.test.tsx`

Expected:
- the new visibility test passes
- existing `App` integration tests remain green

- [ ] **Step 3: Run a build verification**

Run: `cd dashboard/frontend && npm run build`

Expected:
- TypeScript passes
- Vite production build succeeds

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/App.tsx dashboard/frontend/src/App.test.tsx
git commit -m "fix: hide algorithm story on failed runs"
```
