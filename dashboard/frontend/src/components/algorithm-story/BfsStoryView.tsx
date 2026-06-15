import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface BfsStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function BfsStoryView({ step }: BfsStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    graph?: { nodes?: Array<number | string>; edges?: Array<[number | string, number | string]> };
    queue?: Array<number | string>;
    visited?: Array<number | string>;
    distance?: Record<string, number>;
    adjacency?: Record<string, Array<number | string>>;
    current?: number | string | null;
    newly_visited?: Array<number | string>;
    target?: number | string;
    answer?: number | string;
  };

  const nodes = state.graph?.nodes || [];
  const edges = state.graph?.edges || [];
  const queue = state.queue || [];
  const visited = new Set((state.visited || []).map((item) => String(item)));
  const newlyVisited = new Set((state.newly_visited || []).map((item) => String(item)));
  const current = state.current === null || state.current === undefined ? null : String(state.current);
  const distance = state.distance || {};
  const target = state.target === null || state.target === undefined ? null : String(state.target);
  const adjacency = state.adjacency || {};

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas algorithm-story-view__canvas--graph">
        <div className="algorithm-story-graph">
          {edges.length > 0 && (
            <div className="algorithm-story-graph__edges">
              {edges.map((edge, index) => (
                <div key={`edge-${index}`} className="algorithm-story-graph__edge">
                  {String(edge[0])} → {String(edge[1])}
                </div>
              ))}
            </div>
          )}
          <div className="algorithm-story-graph__nodes">
            {nodes.map((node) => {
              const normalized = String(node);
              const isCurrent = normalized === current;
              const isVisited = visited.has(normalized);
              const isNewlyVisited = newlyVisited.has(normalized);
              return (
                <div
                  key={normalized}
                  className={[
                    'algorithm-story-graph__node',
                    isCurrent ? 'algorithm-story-graph__node--current' : '',
                    isVisited ? 'algorithm-story-graph__node--visited' : '',
                    isNewlyVisited ? 'algorithm-story-graph__node--discovered' : '',
                  ].join(' ')}
                >
                  <span className="algorithm-story-graph__nodeMain">{normalized}</span>
                  <span className="algorithm-story-graph__nodeSub">
                    {distance[normalized] !== undefined ? `d=${distance[normalized]}` : 'd=?'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Queue')}</div>
          <div className="algorithm-story-view__chips">
            {queue.length > 0 ? queue.map((item, index) => (
              <span key={`${item}-${index}`} className="algorithm-story-view__chip">{String(item)}</span>
            )) : <span className="algorithm-story-view__empty">{tx('empty')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Visited / New')}</div>
          <div className="algorithm-story-view__chips">
            {visited.size > 0 ? Array.from(visited).map((item) => (
              <span
                key={item}
                className={[
                  'algorithm-story-view__chip',
                  newlyVisited.has(item) ? 'algorithm-story-view__chip--warning' : 'algorithm-story-view__chip--success',
                ].join(' ')}
              >
                {newlyVisited.has(item) ? `${tx('new')} ${item}` : item}
              </span>
            )) : <span className="algorithm-story-view__empty">{tx('none')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Focus')}</div>
          <div className="algorithm-story-view__current">
            {state.answer !== undefined && target ? `${tx('target')} ${target} => ${String(state.answer)}` : current || tx('not started')}
          </div>
          {current && adjacency[current] && (
            <div className="algorithm-story-view__relation">
              {tx('neighbors')}: {adjacency[current].map((item) => String(item)).join(', ')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
