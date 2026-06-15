import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DashboardI18nProvider } from '../i18n';
import type { JourneyStageCard } from '../types/journey';
import SolveJourneyMap from './SolveJourneyMap';

const stages: JourneyStageCard[] = [
  {
    id: 'read_problem',
    order: 1,
    title: 'Read the problem with a deliberately long localized title',
    badge: '01',
    shortDescription: 'Read',
    what: 'Read',
    why: 'Read',
    status: 'completed',
    visits: 1,
    summary: 'This summary is intentionally long so the card can clamp it visually while preserving the full text for hover.',
    evidence: [],
    whyNotes: [],
    steps: [],
  },
  {
    id: 'full_testgen',
    order: 2,
    title: 'Generate tests',
    badge: '02',
    shortDescription: 'Tests',
    what: 'Tests',
    why: 'Tests',
    status: 'waiting',
    visits: 0,
    summary: 'Waiting for tests.',
    evidence: [],
    whyNotes: [],
    steps: [],
  },
];

describe('SolveJourneyMap', () => {
  it('keeps full stage title and summary available as hover text', () => {
    render(
      <DashboardI18nProvider>
        <SolveJourneyMap
          stages={stages}
          activeStageId={null}
          selectedStageId={null}
          mode="live"
          onSelect={vi.fn()}
        />
      </DashboardI18nProvider>,
    );

    const title = screen.getByText(stages[0].title);
    const summary = screen.getByText(stages[0].summary);

    expect(title).toHaveAttribute('title', stages[0].title);
    expect(summary).toHaveAttribute('title', stages[0].summary);
  });
});
