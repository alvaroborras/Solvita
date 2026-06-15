import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface BinarySearchStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function BinarySearchStoryView({ step }: BinarySearchStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    array?: Array<number | string>;
    low?: number;
    high?: number;
    mid?: number;
    target?: number | string;
    comparison?: string;
    value?: number | string;
    next_low?: number | string | null;
    next_high?: number | string | null;
    result?: number | string;
  };

  const values = state.array || [];
  const low = typeof state.low === 'number' ? state.low : -1;
  const high = typeof state.high === 'number' ? state.high : -1;
  const mid = typeof state.mid === 'number' ? state.mid : -1;

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-array">
          {values.map((value, index) => (
            <div
              key={`binary-${index}`}
              className={[
                'algorithm-story-array__cell',
                index === low ? 'algorithm-story-array__cell--left' : '',
                index === high ? 'algorithm-story-array__cell--right' : '',
                index === mid ? 'algorithm-story-array__cell--mid' : '',
              ].join(' ')}
            >
              <span className="algorithm-story-array__value">{String(value)}</span>
              <span className="algorithm-story-array__index">{index}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Bounds')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--info">{tx('low')}: {low}</span>
            <span className="algorithm-story-view__chip algorithm-story-view__chip--mid">mid: {mid}</span>
            <span className="algorithm-story-view__chip algorithm-story-view__chip--warning">{tx('high')}: {high}</span>
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Target Check')}</div>
          <div className="algorithm-story-view__current">{tx('target')} {state.target ?? '—'}</div>
          <div className="algorithm-story-view__relation">{state.comparison ? tx(state.comparison) : tx('not evaluated yet')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--mid">{tx('value')}: {state.value ?? '—'}</span>
            {(state.next_low !== undefined || state.next_high !== undefined) && (
              <span className="algorithm-story-view__chip algorithm-story-view__chip--success">
                {tx('next')}: [{state.next_low ?? low}, {state.next_high ?? high}]
              </span>
            )}
            {state.result !== undefined && (
              <span className="algorithm-story-view__chip algorithm-story-view__chip--success">
                {tx('result index')}: {String(state.result)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
