import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface MonotonicStackStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function MonotonicStackStoryView({ step }: MonotonicStackStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    array?: Array<number | string>;
    stack?: Array<number | string>;
    current_index?: number;
    action?: string;
    popped?: Array<number | string>;
    ans?: Array<number | string | null>;
  };

  const values = state.array || [];
  const currentIndex = typeof state.current_index === 'number' ? state.current_index : -1;
  const stack = state.stack || [];

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-array">
          {values.map((value, index) => (
            <div
              key={`mono-${index}`}
              className={[
                'algorithm-story-array__cell',
                index === currentIndex ? 'algorithm-story-array__cell--mid' : '',
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
          <div className="algorithm-story-view__label">{tx('Monotonic Stack')}</div>
          <div className="algorithm-story-stack">
            {stack.length > 0 ? stack.map((item, index) => (
              <div key={`stack-${index}`} className="algorithm-story-stack__frame">
                {String(item)}
              </div>
            )) : <span className="algorithm-story-view__empty">{tx('empty stack')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Index')}</div>
          <div className="algorithm-story-view__current">{currentIndex >= 0 ? currentIndex : tx('not started')}</div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Action')}</div>
          <div className="algorithm-story-view__relation">{state.action ? tx(state.action) : tx('no action yet')}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Popped / Answer')}</div>
          <div className="algorithm-story-view__chips">
            {(state.popped || []).length > 0 ? (state.popped || []).map((item, index) => (
              <span key={`${item}-${index}`} className="algorithm-story-view__chip algorithm-story-view__chip--warning">
                {tx('pop')} {String(item)}
              </span>
            )) : <span className="algorithm-story-view__empty">{tx('nothing popped')}</span>}
          </div>
          {(state.ans || []).length > 0 && (
            <div className="algorithm-story-view__relation">
              {tx('ans')}: {(state.ans || []).map((item) => (item === null ? '·' : String(item))).join(', ')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
