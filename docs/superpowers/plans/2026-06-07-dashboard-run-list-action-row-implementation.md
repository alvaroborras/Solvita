# Dashboard Run List Action Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `Replay` / `Delete` style actions in the dashboard run list onto a dedicated bottom row so they no longer collide with run metadata.

**Architecture:** Keep the existing `RunList` behavior and data flow unchanged. Only reshape the card layout in `RunList.tsx` so the summary content stays in the top section and the action buttons render in a footer row, then protect that layout contract with a focused component test.

**Tech Stack:** React 18, TypeScript, Testing Library, Vitest, inline component CSS

---

## File Map

- `dashboard/frontend/src/components/RunList.tsx`
  - Owns the run card DOM structure and its co-located CSS.
  - Will be updated so each run card becomes a vertical stack with a dedicated footer action row.
- `dashboard/frontend/src/components/RunList.test.tsx`
  - Owns the focused run-list interaction and layout tests.
  - Will gain a layout contract test that protects the stacked action-row styling.

## Execution Note

The dashboard frontend tree exists in the working tree and is not cleanly available from the isolated worktree used in earlier planning flows. Implement this plan in the main workspace at:

`/ssd-disk/lih/Software-Engineering-work/algorithm-agent`

Do not revert unrelated edits.

### Task 1: Add a failing layout contract test for the stacked action row

**Files:**
- Modify: `dashboard/frontend/src/components/RunList.test.tsx`
- Test: `dashboard/frontend/src/components/RunList.test.tsx`

- [ ] **Step 1: Write the failing test**

Add this test to `dashboard/frontend/src/components/RunList.test.tsx`:

```tsx
  it('renders completed-run actions in a dedicated footer row layout', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/runs' && !init) {
        return Promise.resolve(createResponse({
          runs: [
            {
              run_id: 'done-1',
              problem_name: 'A Very Long Completed Run Name For Layout Testing',
              problem_id: 'done-run',
              started_at: '2026-06-05T15:00:00Z',
              status: 'completed',
              final_status: 'success',
              iterations: 3,
              pass_rate: 1,
            },
          ],
        }));
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    const { container } = render(
      <RunList
        activeRunId={null}
        mode="idle"
        onSelectLive={vi.fn()}
        onSelectReplay={vi.fn()}
      />,
    );

    expect(await screen.findByRole('button', { name: /a very long completed run name for layout testing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /replay/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

    const stylesheet = container.querySelector('style');
    expect(stylesheet?.textContent).toContain('.run-list__item {');
    expect(stylesheet?.textContent).toContain('grid-template-columns: minmax(0, 1fr);');
    expect(stylesheet?.textContent).toContain('.run-list__actions {');
    expect(stylesheet?.textContent).toContain('width: 100%;');
    expect(stylesheet?.textContent).toContain('justify-content: flex-start;');
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd dashboard/frontend && npx vitest run src/components/RunList.test.tsx`

Expected:
- the new layout test fails because `RunList.tsx` still styles `.run-list__item` as a horizontal flex row and does not yet give `.run-list__actions` full-width footer-row layout

- [ ] **Step 3: Commit the failing test checkpoint only if your workflow requires it**

```bash
git add dashboard/frontend/src/components/RunList.test.tsx
git commit -m "test: lock run list action row layout"
```

If your workflow does not want a red-state commit, skip this commit and proceed directly to Task 2.

### Task 2: Implement the stacked run-card layout and verify it

**Files:**
- Modify: `dashboard/frontend/src/components/RunList.tsx`
- Modify: `dashboard/frontend/src/components/RunList.test.tsx`
- Test: `dashboard/frontend/src/components/RunList.test.tsx`

- [ ] **Step 1: Update the run card layout CSS**

In the inline `<style>` block inside `dashboard/frontend/src/components/RunList.tsx`, replace the relevant declarations with:

```css
        .run-list__item {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          align-items: stretch;
          gap: 12px;
          padding: 12px;
          margin-bottom: 8px;
          background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
          border: 1px solid var(--color-border-subtle);
          border-radius: 14px;
          transition: border-color var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
        }
```

```css
        .run-list__select {
          width: 100%;
          min-width: 0;
          border: none;
          background: transparent;
          color: inherit;
          text-align: left;
          cursor: pointer;
        }
```

```css
        .run-list__actions {
          width: 100%;
          display: flex;
          flex-wrap: wrap;
          justify-content: flex-start;
          gap: 8px;
          padding-top: 2px;
        }
```

- [ ] **Step 2: Run the focused run-list tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/components/RunList.test.tsx`

Expected:
- all `RunList` tests pass
- the new layout contract test passes, proving the card is now using a dedicated footer action row

- [ ] **Step 3: Run a build verification**

Run: `cd dashboard/frontend && npm run build`

Expected:
- TypeScript passes
- Vite production build succeeds

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/components/RunList.tsx dashboard/frontend/src/components/RunList.test.tsx
git commit -m "fix: stack dashboard run list actions"
```
