import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface GreedyIntervalStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function GreedyIntervalStoryView({ step }: GreedyIntervalStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    intervals?: Array<{ start: number; end: number; selected?: boolean }>;
    current_index?: number;
    last_end?: number | string;
    decision?: string;
    count?: number | string;
    answer?: number | string;
  };

  const intervals = state.intervals || [];
  const currentIndex = typeof state.current_index === 'number' ? state.current_index : -1;

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-intervals">
          {intervals.map((interval, index) => (
            <div
              key={`interval-${index}`}
              className={[
                'algorithm-story-intervals__card',
                index === currentIndex ? 'algorithm-story-intervals__card--current' : '',
                interval.selected ? 'algorithm-story-intervals__card--selected' : '',
              ].join(' ')}
            >
              <span className="algorithm-story-intervals__label">[{interval.start}, {interval.end}]</span>
              <span className="algorithm-story-intervals__meta">
                {interval.selected ? tx('kept') : tx('candidate')}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current interval')}</div>
          <div className="algorithm-story-view__current">
            {currentIndex >= 0 ? `#${currentIndex}` : tx('not selected')}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Last chosen end')}</div>
          <div className="algorithm-story-view__current">{state.last_end ?? '—'}</div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Decision')}</div>
          <div className="algorithm-story-view__relation">{state.decision ? tx(state.decision) : tx('not evaluated yet')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--success">
              {tx('chosen count')}: {state.count ?? 0}
            </span>
            {state.answer !== undefined && (
              <span className="algorithm-story-view__chip algorithm-story-view__chip--info">
                {tx('final answer')}: {String(state.answer)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
