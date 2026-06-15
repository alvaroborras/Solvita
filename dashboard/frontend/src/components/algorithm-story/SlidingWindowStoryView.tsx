import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface SlidingWindowStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function SlidingWindowStoryView({ step }: SlidingWindowStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    array?: Array<number | string>;
    left?: number;
    right?: number;
    window_sum?: number | string;
    condition?: string;
    window_elements?: Array<number | string>;
    best_length?: number | string;
    target?: number | string;
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
              key={`window-${index}`}
              className={[
                'algorithm-story-array__cell',
                index >= left && index <= right ? 'algorithm-story-array__cell--window' : '',
                index === left ? 'algorithm-story-array__cell--left' : '',
                index === right ? 'algorithm-story-array__cell--right' : '',
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
          <div className="algorithm-story-view__label">{tx('Window')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--info">{tx('left')}: {left}</span>
            <span className="algorithm-story-view__chip algorithm-story-view__chip--warning">{tx('right')}: {right}</span>
          </div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current State')}</div>
          <div className="algorithm-story-view__current">
            {tx('sum')} {state.window_sum ?? '—'} / {tx('target')} {state.target ?? '—'}
          </div>
          <div className="algorithm-story-view__relation">{state.condition ? tx(state.condition) : tx('window not evaluated yet')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip algorithm-story-view__chip--success">
              {tx('best length')}: {state.best_length ?? '—'}
            </span>
          </div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Window Elements')}</div>
          <div className="algorithm-story-view__chips">
            {(state.window_elements || []).length > 0 ? (state.window_elements || []).map((item, index) => (
              <span key={`${item}-${index}`} className="algorithm-story-view__chip">{String(item)}</span>
            )) : <span className="algorithm-story-view__empty">{tx('empty window')}</span>}
          </div>
          {state.answer !== undefined && (
            <div className="algorithm-story-view__relation">{tx('final answer')}: {String(state.answer)}</div>
          )}
        </div>
      </div>
    </div>
  );
}
