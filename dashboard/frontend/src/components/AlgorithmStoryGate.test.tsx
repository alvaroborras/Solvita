import { useEffect } from 'react';
import type { ReactElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { DashboardI18nProvider, useI18n } from '../i18n';
import AlgorithmStoryGate from './AlgorithmStoryGate';
import type { AlgorithmVisualization } from '../types/artifacts';

function createStory(
  overrides: Partial<AlgorithmVisualization> = {},
): AlgorithmVisualization {
  return {
    supported: true,
    family: 'bfs',
    mode: 'showcase',
    sampleSource: 'unit-test',
    sampleFocus: '',
    sampleInput: '',
    sampleOutput: '',
    title: 'Breadth-first search walkthrough',
    summary: 'Trace the queue while BFS visits the graph.',
    steps: [
      {
        step: 1,
        label: 'Start at node 1',
        caption: 'Initialize the queue with the starting node.',
        state: {
          n: 3,
          m: 2,
          edges: [[1, 2], [2, 3]],
          adjacency: { '1': [2], '2': [1, 3], '3': [2] },
          queue: [1],
          visited: [1],
          distance: { '1': 0, '2': -1, '3': -1 },
        },
      },
    ],
    fallbackText: '',
    ...overrides,
  };
}

function ForceChinese() {
  const { setLanguage } = useI18n();
  useEffect(() => {
    setLanguage('zh');
  }, [setLanguage]);
  return null;
}

function renderInChinese(ui: ReactElement) {
  return render(
    <DashboardI18nProvider>
      <ForceChinese />
      {ui}
    </DashboardI18nProvider>,
  );
}

describe('AlgorithmStoryGate', () => {
  afterEach(() => {
    cleanup();
  });

  it('shows only the small placeholder when the story family is unsupported', () => {
    renderInChinese(<AlgorithmStoryGate story={createStory({ supported: false, family: 'unsupported', steps: [] })} />);

    const gate = document.querySelector('.algorithm-story-gate');
    expect(gate).toBeInTheDocument();
    expect(screen.getByText('该题暂无 family 级过程演示。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(screen.queryByText('Algorithm Story')).not.toBeInTheDocument();
  });

  it('shows the unsupported placeholder in English by default', () => {
    render(<AlgorithmStoryGate story={createStory({ supported: false, family: 'unsupported', steps: [] })} />);

    expect(screen.getByText('No family-level walkthrough is available for this problem.')).toBeInTheDocument();
    expect(screen.queryByText('该题暂无 family 级过程演示。')).not.toBeInTheDocument();
  });

  it('shows the detected family when steps are missing and hides playback controls', () => {
    renderInChinese(<AlgorithmStoryGate story={createStory({ family: 'bfs', steps: [] })} />);

    expect(screen.getByText('已识别为 bfs，但本次运行未生成足够的过程轨迹。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Prev' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
  });

  it('falls back to the placeholder when a malformed story payload has non-array steps', () => {
    const malformedStory = {
      ...createStory(),
      steps: null,
    } as unknown as AlgorithmVisualization;

    renderInChinese(<AlgorithmStoryGate story={malformedStory} />);

    expect(screen.getByText('已识别为 bfs，但本次运行未生成足够的过程轨迹。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
  });

  it('falls back to the generic placeholder when the family label is missing', () => {
    const malformedStory = {
      ...createStory(),
      family: '' as unknown as AlgorithmVisualization['family'],
      steps: [],
    };

    renderInChinese(<AlgorithmStoryGate story={malformedStory} />);

    expect(screen.getByText('该题暂无 family 级过程演示。')).toBeInTheDocument();
    expect(screen.queryByText(/已识别为/)).not.toBeInTheDocument();
  });

  it('renders the real AlgorithmStoryCard when the story has playable steps', () => {
    render(<AlgorithmStoryGate story={createStory()} mode="replay" revision={2} />);

    expect(screen.getByText('Algorithm Story')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Breadth-first search walkthrough' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
    expect(screen.queryByText('该题暂无 family 级过程演示。')).not.toBeInTheDocument();
  });
});
