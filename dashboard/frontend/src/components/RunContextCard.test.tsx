import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import RunContextCard from './RunContextCard';

describe('RunContextCard', () => {
  afterEach(() => {
    cleanup();
  });

  it('shows the showcase chip when the run payload exposes is_showcase metadata', () => {
    render(
      <RunContextCard
        mode="live"
        runId="run-1"
        problemName="Demo"
        problem={{
          description: 'Demo statement',
          _metadata: {
            name: 'Demo',
            source: 'sample',
            is_showcase: true,
          },
        }}
        config={{ max_iterations: 5 }}
        eventCount={3}
        stageCount={7}
        touchedStageCount={2}
        completedStageCount={1}
        currentStageLabel="Codegen"
        finalStatus={null}
      />,
    );

    expect(screen.getByText('showcase')).toBeInTheDocument();
  });

  it('shows abstract phase tags interpreted by the Agent', () => {
    render(
      <RunContextCard
        mode="live"
        runId="run-abstract"
        problemName="Graph Walk"
        problem={{
          description: 'Find reachable nodes.',
          _metadata: { name: 'Graph Walk', source: 'custom' },
        }}
        config={{ max_iterations: 5 }}
        abstractInsight={{ tags: ['graphs', 'bfs'], confidence: 0.83 }}
        eventCount={4}
        stageCount={7}
        touchedStageCount={1}
        completedStageCount={1}
        currentStageLabel="Read Problem"
        finalStatus={null}
      />,
    );

    expect(screen.getByText('Abstract tags')).toBeInTheDocument();
    expect(screen.getByText('graphs')).toBeInTheDocument();
    expect(screen.getByText('bfs')).toBeInTheDocument();
    expect(screen.getByText('83% confidence')).toBeInTheDocument();
  });

  it('shows run-focused live narrative instead of the raw problem description', () => {
    const rawProblemDescription = 'Given an array of integers, find the first pair that sums to the target value.';

    render(
      <RunContextCard
        mode="live"
        runId="run-2"
        problemName="Pair Sum"
        problem={{
          description: rawProblemDescription,
          public_tests: [{ input: '4\n1 2 3 4\n5\n', output: '1 4\n' }],
          _metadata: {
            name: 'Pair Sum',
            source: 'sample',
          },
        }}
        config={{ max_iterations: 5 }}
        eventCount={6}
        stageCount={7}
        touchedStageCount={3}
        completedStageCount={1}
        currentStageLabel="Generate candidate solution"
        finalStatus={null}
      />,
    );

    expect(screen.getByText(/Live run is currently in Generate candidate solution\./i)).toBeInTheDocument();
    expect(screen.getByText(/AlgoPilot is still working through the active attempt, so this card stays focused on run progress instead of repeating the full prompt\./i)).toBeInTheDocument();
    expect(screen.queryByText(rawProblemDescription)).not.toBeInTheDocument();
  });
});
