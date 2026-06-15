import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface UnionFindStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function UnionFindStoryView({ step }: UnionFindStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    groups?: Array<Array<number | string>>;
    current_union?: string;
    components?: number | string;
    edges_processed?: number | string;
    output?: number | string;
  };

  const groups = state.groups || [];
  const currentUnionNodes = new Set(String(state.current_union || '').split('-').filter(Boolean));

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-groups">
          {groups.length > 0 ? groups.map((group, index) => (
            <div
              key={`group-${index}`}
              className={[
                'algorithm-story-group',
                currentUnionNodes.size > 0 && group.some((node) => currentUnionNodes.has(String(node))) ? 'algorithm-story-group--active' : '',
              ].join(' ')}
            >
              <div className="algorithm-story-group__title">{tx('component')} {index + 1}</div>
              <div className="algorithm-story-group__nodes">
                {group.map((node) => (
                  <span key={`${index}-${String(node)}`} className="algorithm-story-group__node">
                    {String(node)}
                  </span>
                ))}
              </div>
            </div>
          )) : <div className="algorithm-story-view__empty">{tx('no components emitted')}</div>}
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Union')}</div>
          <div className="algorithm-story-view__current">{state.current_union || tx('none')}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Components')}</div>
          <div className="algorithm-story-view__current">{state.components ?? '—'}</div>
        </div>
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Progress')}</div>
          <div className="algorithm-story-view__chips">
            <span className="algorithm-story-view__chip">{tx('processed edges')}: {state.edges_processed ?? 0}</span>
            {state.output !== undefined && (
              <span className="algorithm-story-view__chip algorithm-story-view__chip--success">
                {tx('final answer')}: {String(state.output)}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
