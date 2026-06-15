import { cleanup, render, screen, within } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import ProblemStatementCard from './ProblemStatementCard';

const fullProblem = {
  description: `Problem
This is the first paragraph of the statement.

This is the second paragraph with more detail.

Input Format
The first line contains n.
The second line contains n integers.

Output Format
Print the maximum score.

Constraints
1 <= n <= 200000

Complexity
Expected time complexity: O(n log n)
Expected space complexity: O(n)

Explanation
Sort the values, then evaluate the best pair.

Sample Input 1
5
1 4 2 8 6

Sample Output 1
14

Sample Input 2
3
9 1 5

Sample Output 2
14`,
  time_limit: 2000,
  space_limit: 512,
  _metadata: {
    name: 'Maximum Score Pair',
    source: 'codeforces',
    family: 'greedy',
    difficulty: '1800',
  },
};

function getByExactTextContent(value: string): HTMLElement {
  return screen.getByText((_, element) => element?.textContent === value);
}

describe('ProblemStatementCard', () => {
  afterEach(() => {
    cleanup();
  });

  it('applies the non-truncating readable text contract to long body and code blocks', () => {
    const longStatement = 'LONG_SEGMENT '.repeat(80).trim();
    const longInput = 'INPUT_SEGMENT '.repeat(40).trim();
    const longBody = `Problem
${longStatement}

Input Format
${longInput}`;

    render(
      <ProblemStatementCard
        problem={{
          description: longBody,
          _metadata: {
            name: 'Long Statement',
          },
        }}
      />,
    );

    const bodyText = screen.getByTestId('statement-card-body-0');
    const codeText = screen.getByTestId('statement-card-input-format');

    expect(bodyText).toHaveClass('statement-card__bodyText');
    expect(bodyText.textContent).toBe(longStatement);
    expect(bodyText).toHaveStyle({
      whiteSpace: 'pre-wrap',
      textOverflow: 'clip',
      overflow: 'visible',
      wordBreak: 'break-word',
    });

    expect(codeText).toHaveClass('statement-card__code');
    expect(codeText.textContent).toBe(longInput);
    expect(codeText).toHaveStyle({
      whiteSpace: 'pre-wrap',
      textOverflow: 'clip',
      overflow: 'visible',
      wordBreak: 'break-word',
    });
  });

  it('renders full mode sections, chips, and sample data', () => {
    render(<ProblemStatementCard problem={fullProblem} mode="full" />);

    expect(screen.getByText('Problem Statement')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Maximum Score Pair' })).toBeInTheDocument();

    const chips = screen.getByText('codeforces').closest('.statement-card__chips');
    expect(chips).not.toBeNull();
    expect(within(chips as HTMLElement).getByText('codeforces')).toBeInTheDocument();
    expect(within(chips as HTMLElement).getByText('greedy')).toBeInTheDocument();
    expect(within(chips as HTMLElement).getByText('1800')).toBeInTheDocument();
    expect(within(chips as HTMLElement).getByText('2000 ms')).toBeInTheDocument();
    expect(within(chips as HTMLElement).getByText('512 MB')).toBeInTheDocument();

    expect(screen.getByText('Problem')).toBeInTheDocument();
    expect(screen.getByText(/This is the first paragraph of the statement\./)).toBeInTheDocument();
    expect(screen.getByText('Input Format')).toBeInTheDocument();
    expect(getByExactTextContent('The first line contains n.\nThe second line contains n integers.')).toBeInTheDocument();
    expect(screen.getByText('Output Format')).toBeInTheDocument();
    expect(screen.getByText('Print the maximum score.')).toBeInTheDocument();
    expect(screen.getByText('Constraints')).toBeInTheDocument();
    expect(screen.getByText('1 <= n <= 200000')).toBeInTheDocument();
    expect(screen.getByText('Complexity')).toBeInTheDocument();
    expect(screen.getByText(/Expected time complexity: O\(n log n\)/)).toBeInTheDocument();
    expect(screen.getByText('Explanation')).toBeInTheDocument();
    expect(screen.getByText('Sort the values, then evaluate the best pair.')).toBeInTheDocument();

    const samples = screen.getByText('Sample 1').closest('.statement-card__sample')?.parentElement;
    expect(samples).not.toBeNull();
    expect(screen.getByText('Sample 1')).toBeInTheDocument();
    expect(screen.getByText('Sample 2')).toBeInTheDocument();
    expect(screen.getAllByText('Input')).toHaveLength(2);
    expect(screen.getAllByText('Output')).toHaveLength(2);
    expect(getByExactTextContent('5\n1 4 2 8 6')).toBeInTheDocument();
    expect(screen.getAllByText('14')).toHaveLength(2);
    expect(getByExactTextContent('3\n9 1 5')).toBeInTheDocument();
  });

  it('renders compact mode with preview kicker and full content semantics', () => {
    render(<ProblemStatementCard problem={fullProblem} mode="compact" />);

    const card = screen.getByText('Problem Preview').closest('.statement-card');
    expect(card).toHaveClass('statement-card--compact');
    expect(screen.getByRole('heading', { name: 'Maximum Score Pair' })).toBeInTheDocument();
    expect(screen.getByText('Input Format')).toBeInTheDocument();
    expect(screen.getByText('Output Format')).toBeInTheDocument();
    expect(screen.getByText('Constraints')).toBeInTheDocument();
    expect(screen.getByText('Complexity')).toBeInTheDocument();
    expect(screen.getByText('Explanation')).toBeInTheDocument();
    expect(screen.getByText('Sample 1')).toBeInTheDocument();
    expect(getByExactTextContent('5\n1 4 2 8 6')).toBeInTheDocument();
    expect(screen.getAllByText('14')).toHaveLength(2);
  });

  it('uses theme tokens for statement chips and code/sample surfaces', () => {
    const stylesheet = readFileSync(resolve(process.cwd(), 'src/styles/journey.css'), 'utf8');
    const statementCardStart = stylesheet.indexOf('.statement-card');
    const statementCardEnd = stylesheet.indexOf('.final-summary', statementCardStart);
    const statementCardCss = stylesheet.slice(statementCardStart, statementCardEnd);

    expect(statementCardCss).toContain('background: var(--color-pill-bg)');
    expect(statementCardCss).toContain('background: var(--color-bg-secondary)');
    expect(statementCardCss).toContain('border: 1px solid var(--color-border-subtle)');
    expect(statementCardCss).not.toContain('background: rgba(255, 255, 255, 0.04)');
    expect(statementCardCss).not.toContain('background: rgba(255, 255, 255, 0.06)');
    expect(statementCardCss).not.toContain('border: 1px solid rgba(255, 255, 255, 0.06)');
  });
});
