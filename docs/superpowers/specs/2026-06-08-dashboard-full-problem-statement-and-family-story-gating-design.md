# Dashboard Full Problem Statement And Family Story Gating Design

## Goal

Improve the AlgoPilot dashboard so that:

1. The user can read a complete problem statement in the frontend, including the main statement, sample input/output, and practical limits such as time/memory constraints.
2. Family-specific step-by-step teaching playback is shown only when the problem actually falls into a supported family and the run produced real story data.
3. The teaching playback must feel run-specific and problem-specific rather than like a static canned demo for each family.

This design applies to two dashboard surfaces:

- the `Start Solve` problem preview flow
- the active run page

## Non-Goals

- No backend schema migration for problem statements in this iteration.
- No requirement to infer perfect semantic structure from every free-form statement.
- No family playback inside the `Start Solve` preview flow.
- No expansion of supported families in this design; only gating and presentation behavior change.

## Current Problems

### Problem statement visibility is incomplete

The current run context card truncates `problem.description` and shows only a short preview. That is not enough for users who want to inspect the whole statement while the agent is solving.

The `Start Solve` browse preview also only shows a lightweight preview string, not the full statement and sample details.

### Family playback appears too eagerly

The current algorithm story card still renders a fallback story section even when a run is unsupported or has no usable playback steps. This does not match the requirement that only supported family problems should show concrete solving-process playback.

### Playback can look too template-like

The current frontend already uses per-family renderers, but the product requirement now needs a stricter guarantee: renderers may reuse a family-specific visual grammar, but they must only animate and explain data that came from the current run artifact.

## Product Requirements

### Requirement 1: Full statement visibility

The dashboard must show a complete readable problem statement in both of these places:

- `Start Solve` preview, using a compact but complete layout
- active run page, using a fuller reading layout

The display must support:

- statement title
- statement body
- input format
- output format
- constraints
- complexity guidance if explicitly present in the statement
- public sample cases from `public_tests`
- metadata such as source, family, difficulty, time limit, and memory limit

If a field is absent, the UI must omit that block cleanly rather than rendering placeholders or empty headings.

The statement body must remain fully readable even when it is long. The dashboard must not replace long problem text with an ellipsis-based preview on either the `Start Solve` preview or the active run page.

### Requirement 2: Family playback gating

The active run page must display full teaching playback only when all of the following are true:

- `algorithmVisualization.supported === true`
- `algorithmVisualization.family !== "unsupported"`
- `algorithmVisualization.steps.length > 0`

If any of those checks fail, the dashboard must not show the playback timeline, controls, or fake steps. Instead it must show a very small explanatory placeholder, for example:

`该题暂无 family 级过程演示。`

### Requirement 3: Dynamic, run-specific playback

For supported runs, the playback must be driven only by the current run artifact data:

- `steps`
- `sampleInput`
- `sampleOutput`
- `sampleSource`
- `sampleFocus`
- `traceSource`
- `validationNote`

The family renderer can control the visual language for that family, but it must not fabricate step content. Two different BFS runs should still look different because the displayed queue state, node order, sample mapping, and state changes come from the run-specific artifact.

## Proposed Architecture

### 1. Statement parsing layer

Add a frontend-only parsing utility that converts a raw `problem` object into a structured statement view model.

Input sources:

- `problem.description`
- `problem.public_tests`
- `problem.time_limit`
- `problem.space_limit`
- `problem._metadata`

Output structure:

- `title`
- `bodySections`
- `inputFormat`
- `outputFormat`
- `constraints`
- `complexity`
- `explanation`
- `samples`
- `meta`

The parser is best-effort, not authoritative. It should recognize common Chinese and English headings, including:

- `题目描述`
- `输入格式`
- `输出格式`
- `样例`
- `样例输入`
- `样例输出`
- `说明`
- `约束`
- `复杂度`
- `Problem`
- `Input`
- `Output`
- `Sample`
- `Example`
- `Explanation`
- `Constraints`
- `Complexity`

If no structure can be extracted reliably, the parser must fall back to:

- full original statement text as the primary body
- `public_tests` rendered as samples
- `time_limit` and `space_limit` rendered as limits

The parser must never discard statement text just because it could not classify it.

### 2. Dedicated statement presentation component

Add a dedicated `ProblemStatementCard` component.

Responsibilities:

- render the structured statement view model
- support a compact mode for `Start Solve`
- support a full mode for the active run page
- show samples in a stable readable layout
- show time/memory limits when present

Non-responsibilities:

- it should not own run-state progress information
- it should not decide whether family playback should appear

### 3. Keep run context and statement display separate

`RunContextCard` should remain focused on run identity and progress:

- run id
- mode
- status
- stage progress
- small metadata chips

It should no longer be the place where the full statement is rendered.

This keeps page boundaries clear:

- `RunContextCard` explains the run
- `ProblemStatementCard` explains the problem

### 4. Story gating wrapper

Add a small gate component around `AlgorithmStoryCard`.

Responsibilities:

- decide whether the run has supported family playback
- render the real story card only when playback data is valid
- otherwise render a small placeholder explanation

Suggested behavior:

- supported family + non-empty steps: render `AlgorithmStoryCard`
- supported family + empty steps: render small placeholder saying playback data is unavailable for this run
- unsupported family: render small placeholder saying no family-level playback is available

This keeps `AlgorithmStoryCard` focused on rendering playback rather than deciding whether playback exists.

## Page Layout Changes

### Active run page

Recommended order:

1. hero / current run summary
2. solve journey map
3. live progress panels
4. `RunContextCard`
5. `ProblemStatementCard`
6. story gate (`AlgorithmStoryCard` or small placeholder)
7. final summary
8. failure analysis
9. timeline
10. evidence workbench

Rationale:

- users should see the whole problem before they interpret a solving-process demo
- the page should move from high-level run status to problem content to deeper analysis

### Start Solve preview

The selected problem preview in `ProblemPanel` should be upgraded from a short preview string to a compact statement card that reuses the same parsing logic.

This compact view should still prioritize scan speed, but it must include:

- title
- source/family/difficulty chips
- full statement text without truncating it into an ellipsis preview
- public samples
- time/memory limits if present

No family playback belongs in this surface.

## Rendering Rules

### Problem statement rendering

- Preserve line breaks and paragraph grouping where possible.
- Render code-like blocks such as sample input/output in `<pre>` style blocks.
- Hide empty sections.
- Do not truncate long statement text with `...` or a fixed preview length.
- If the statement is long, solve the layout problem with vertical flow, sectioning, or a readable container, not by removing statement content.
- If multiple samples exist, render them in order and label them clearly.
- If `public_tests` exist but the description already contains sample sections, keep both sources consistent:
  - description-derived samples take precedence for presentation order when clearly extractable
  - `public_tests` remain the canonical fallback sample source

### Story placeholder rendering

The placeholder for unsupported or non-playable runs should be intentionally small and visually secondary. It should not look like a broken card or an empty interactive module.

The placeholder is explanatory, not apologetic. It should say what is unavailable, not imply an error.

## Error Handling And Fallbacks

### Statement parsing failure

If the parser cannot confidently segment the statement:

- render the entire original text under the statement body
- still render `public_tests`
- still render time/memory limits
- do not throw
- do not suppress content

### Partial statement structure

If some sections are extractable and others are not:

- render the extracted sections explicitly
- append the remaining unclassified text as a general statement section

### Missing playback data

If the run has a supported family but missing or empty steps:

- do not synthesize steps
- do not render disabled controls
- show the small placeholder only

## Test Plan

### Parser tests

Add tests that verify:

- Chinese statements can extract input/output/constraints/samples
- English statements can extract input/output/constraints/samples
- free-form statements without headings still preserve full text
- limits from `time_limit` and `space_limit` are exposed even when the statement is unstructured

### Component tests

Add tests that verify:

- the active run page renders a full statement card from the current run problem
- the `Start Solve` preview renders a compact but complete statement card
- unsupported family runs show only the small placeholder
- supported family runs with `steps=[]` show only the small placeholder
- supported family runs with real steps render the full story card

### Regression tests

Add tests that verify:

- no statement text is lost when parsing fails
- story playback does not render controls when the gate blocks it
- existing supported story families still render their family-specific views when valid data exists

## Risks And Tradeoffs

### Risk: statement parsing can never be perfect

This is acceptable in this iteration because the fallback behavior is complete-content preservation, not structural perfection.

### Risk: more vertical space on the run page

This is intentional. The product goal explicitly prioritizes readable full statements. The page should optimize for actual problem solving rather than minimal height.

### Risk: supported family but poor trace quality

The gate solves the misleading UI problem by refusing to show fake or empty playback. A small placeholder is more honest than a generic canned animation.

## Acceptance Criteria

This design is complete when all of the following are true:

- users can read the full statement in both `Start Solve` preview and the active run page
- long statements are still shown in full and are not collapsed into an ellipsis-only preview
- sample input/output and limits are visible when present
- unsupported family runs do not render full algorithm playback
- supported family runs render playback only when real step data exists
- the visible playback content is tied to the current run artifact rather than to a static family template alone
