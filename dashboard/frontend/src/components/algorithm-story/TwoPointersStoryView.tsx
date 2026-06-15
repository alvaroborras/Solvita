import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface TwoPointersStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function TwoPointersStoryView({ step }: TwoPointersStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    array?: Array<number | string>;
    left?: number;
    right?: number;
    target?: number | string;
    current_sum?: number | string;
    relation?: string;
    action?: string;
    left_value?: number | string;
    right_value?: number | string;
    answer?: number | string;
  };

  const values = state.array || [];
  const left = typeof state.left === 'number' ? state.left : -1;
  const right = typeof state.right === 'number' ? state.right : -1;

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-array">
          {values.map((value, index) => (
            <div
              key={`array-${index}`}
              className={[
                'algorithm-story-array__cell',
                index === left ? 'algorithm-story-array__cell--left' : '',
                index === right ? 'algorithm-story-array__cell--right' : '',
                index === left && index === right ? 'algorithm-story-array__cell--both' : '',
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
          <div className="algorithm-story-view__label">{tx('Pointers')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--info">{tx('left')}: {left}</span>
            <span className="algorithm-story-view__chip algorithm-story-view__chip--warning">{tx('right')}: {right}</span>
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Check')}</div>
          <div className="algorithm-story-view__current">
            {tx('sum')} {state.current_sum ?? '—'} {tx('vs target')} {state.target ?? '—'}
          </div>
          <div className="algorithm-story-view__relation">{state.relation ? tx(state.relation) : tx('not evaluated yet')}</div>
          {(state.left_value !== undefined || state.right_value !== undefined) && (
            <div className="algorithm-story-view__chips">
              <span className="algorithm-story-view__chip algorithm-story-view__chip--info">{tx('left value')}: {state.left_value ?? '—'}</span>
              <span className="algorithm-story-view__chip algorithm-story-view__chip--warning">{tx('right value')}: {state.right_value ?? '—'}</span>
            </div>
          )}
          {(state.action || state.answer !== undefined) && (
            <div className="algorithm-story-view__relation">
              {state.answer !== undefined ? `${tx('answer')}: ${String(state.answer)}` : tx(state.action || '')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
