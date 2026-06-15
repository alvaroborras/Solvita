import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface TopologicalSortStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function TopologicalSortStoryView({ step }: TopologicalSortStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    graph?: { nodes?: Array<number | string>; edges?: Array<[number | string, number | string]> };
    indegree?: Record<string, number>;
    queue?: Array<number | string>;
    current?: number | string | null;
    processed?: Array<number | string>;
  };

  const nodes = state.graph?.nodes || [];
  const edges = state.graph?.edges || [];
  const queue = state.queue || [];
  const processed = new Set((state.processed || []).map((item) => String(item)));
  const current = state.current === null || state.current === undefined ? null : String(state.current);
  const indegree = state.indegree || {};

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas algorithm-story-view__canvas--graph">
        <div className="algorithm-story-graph">
          {edges.length > 0 && (
            <div className="algorithm-story-graph__edges">
              {edges.map((edge, index) => (
                <div key={`topo-edge-${index}`} className="algorithm-story-graph__edge">
                  {String(edge[0])} → {String(edge[1])}
                </div>
              ))}
            </div>
          )}
          <div className="algorithm-story-graph__nodes">
            {nodes.map((node) => {
              const normalized = String(node);
              const isCurrent = normalized === current;
              const isProcessed = processed.has(normalized);
              return (
                <div
                  key={normalized}
                  className={[
                    'algorithm-story-graph__node',
                    isCurrent ? 'algorithm-story-graph__node--current' : '',
                    isProcessed ? 'algorithm-story-graph__node--visited' : '',
                  ].join(' ')}
                >
                  <span className="algorithm-story-graph__nodeMain">{normalized}</span>
                  <span className="algorithm-story-graph__nodeSub">in={indegree[normalized] ?? 0}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Zero-indegree queue')}</div>
          <div className="algorithm-story-view__chips">
            {queue.length > 0 ? queue.map((item, index) => (
              <span key={`${item}-${index}`} className="algorithm-story-view__chip">{String(item)}</span>
            )) : <span className="algorithm-story-view__empty">{tx('empty')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Processed order')}</div>
          <div className="algorithm-story-view__chips">
            {processed.size > 0 ? Array.from(processed).map((item) => (
              <span key={item} className="algorithm-story-view__chip algorithm-story-view__chip--success">{item}</span>
            )) : <span className="algorithm-story-view__empty">{tx('none yet')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Node')}</div>
          <div className="algorithm-story-view__current">{current || tx('not selected')}</div>
          <div className="algorithm-story-view__relation">
            {queue.length > 0 ? `${tx('next available')}: ${queue.join(', ')}` : tx('no unlocked node remains')}
          </div>
        </div>
      </div>
    </div>
  );
}
