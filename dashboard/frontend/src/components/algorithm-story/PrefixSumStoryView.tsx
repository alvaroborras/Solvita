import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface PrefixSumStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function PrefixSumStoryView({ step }: PrefixSumStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    array?: Array<number | string>;
    prefix?: Array<number | string>;
    running_total?: number | string;
    query?: string;
    range?: { l?: number; r?: number } | null;
    prefix_highlights?: Array<number | string>;
    answer?: number | string;
  };

  const values = state.array || [];
  const prefix = state.prefix || [];
  const rangeLeft = typeof state.range?.l === 'number' ? state.range.l : -1;
  const rangeRight = typeof state.range?.r === 'number' ? state.range.r : -1;
  const prefixHighlights = new Set((state.prefix_highlights || []).map((item) => Number(item)));

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-prefix">
          <div className="algorithm-story-prefix__row">
            {values.map((value, index) => (
              <div
                key={`value-${index}`}
                className={[
                  'algorithm-story-prefix__cell',
                  index >= rangeLeft && index <= rangeRight ? 'algorithm-story-prefix__cell--range' : '',
                ].join(' ')}
              >
                <span className="algorithm-story-prefix__label">a[{index}]</span>
                <span className="algorithm-story-prefix__value">{String(value)}</span>
              </div>
            ))}
          </div>
          <div className="algorithm-story-prefix__row">
            {prefix.map((value, index) => (
              <div
                key={`prefix-${index}`}
                className={[
                  'algorithm-story-prefix__cell',
                  prefixHighlights.has(index) ? 'algorithm-story-prefix__cell--active' : '',
                ].join(' ')}
              >
                <span className="algorithm-story-prefix__label">pref[{index}]</span>
                <span className="algorithm-story-prefix__value">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Running Total')}</div>
          <div className="algorithm-story-view__current">{state.running_total ?? '—'}</div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Query / Use')}</div>
          <div className="algorithm-story-view__relation">{state.query ? tx(state.query) : tx('building prefix values')}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Range Answer')}</div>
          <div className="algorithm-story-view__current">{state.answer ?? tx('not answered yet')}</div>
        </div>
      </div>
    </div>
  );
}
