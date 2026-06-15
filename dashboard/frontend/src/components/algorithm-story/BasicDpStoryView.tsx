import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface BasicDpStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function BasicDpStoryView({ step }: BasicDpStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    table?: Array<Array<number | string | null>>;
    highlight_cells?: Array<[number, number]>;
    current_transition?: string;
    input_view?: Record<string, unknown>;
    answer?: number | string;
  };

  const table = state.table || [];
  const highlights = new Set((state.highlight_cells || []).map(([row, col]) => `${row}:${col}`));

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        {table.length > 0 ? (
          <div className="algorithm-story-dp">
            {table.map((row, rowIndex) => (
              <div key={`row-${rowIndex}`} className="algorithm-story-dp__row">
                {row.map((cell, colIndex) => (
                  <div
                    key={`cell-${rowIndex}-${colIndex}`}
                    className={[
                      'algorithm-story-dp__cell',
                      highlights.has(`${rowIndex}:${colIndex}`) ? 'algorithm-story-dp__cell--active' : '',
                    ].join(' ')}
                  >
                    {cell === null || cell === undefined ? '·' : String(cell)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="algorithm-story-view__empty">{tx('No DP table emitted for this step.')}</div>
        )}
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Transition')}</div>
          <div className="algorithm-story-view__current">{state.current_transition ? tx(state.current_transition) : tx('not specified')}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Best Answer')}</div>
          <div className="algorithm-story-view__current">{state.answer ?? tx('still filling the table')}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Input View')}</div>
          <pre className="algorithm-story-view__state">{JSON.stringify(state.input_view || {}, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}
