import { AlgorithmStoryStep } from '../../types/artifacts';
import { useStoryText } from './useStoryText';

interface DfsRecursionStoryViewProps {
  step: AlgorithmStoryStep;
}

export default function DfsRecursionStoryView({ step }: DfsRecursionStoryViewProps) {
  const tx = useStoryText();
  const state = step.state as {
    tree?: { nodes?: Array<string>; edges?: Array<[string, string]> };
    call_stack?: Array<Record<string, unknown>>;
    current_call?: Record<string, unknown> | null;
    returned_values?: Record<string, unknown>;
    highlighted_nodes?: Array<string>;
  };

  const callStack = state.call_stack || [];
  const currentCall = state.current_call || null;
  const treeNodes = state.tree?.nodes || [];
  const treeEdges = state.tree?.edges || [];
  const returnedValues = state.returned_values || {};
  const highlightedNodes = new Set((state.highlighted_nodes || []).map((item) => String(item)));
  const currentNode = currentCall?.id === null || currentCall?.id === undefined ? null : String(currentCall.id);

  return (
    <div className="algorithm-story-view">
      <div className="algorithm-story-view__canvas">
        <div className="algorithm-story-tree">
          {treeNodes.length > 0 ? (
            <>
              <div className="algorithm-story-tree__nodes">
                {treeNodes.map((node) => (
                  <div
                    key={node}
                    className={[
                      'algorithm-story-tree__node',
                      currentNode === node ? 'algorithm-story-tree__node--current' : '',
                      highlightedNodes.has(node) ? 'algorithm-story-tree__node--visited' : '',
                    ].join(' ')}
                  >
                    {node}
                  </div>
                ))}
              </div>
              <div className="algorithm-story-tree__edges">
                {treeEdges.map((edge, index) => (
                  <div key={`edge-${index}`} className="algorithm-story-tree__edge">
                    {edge[0]} → {edge[1]}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="algorithm-story-view__empty">{tx('No recursion tree emitted for this step.')}</div>
          )}
        </div>
      </div>

      <div className="algorithm-story-view__aside">
        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Call Stack')}</div>
          <div className="algorithm-story-stack">
            {callStack.length > 0 ? callStack.map((frame, index) => (
              <div key={`frame-${index}`} className="algorithm-story-stack__frame">
                {String(frame.name || frame.id || `frame ${index + 1}`)}
              </div>
            )) : <span className="algorithm-story-view__empty">{tx('stack empty')}</span>}
          </div>
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Current Call')}</div>
          <div className="algorithm-story-view__current">{currentNode ? `dfs(${currentNode})` : tx('returning')}</div>
          {highlightedNodes.size > 0 && (
            <div className="algorithm-story-view__chips">
              {Array.from(highlightedNodes).map((node) => (
                <span key={node} className="algorithm-story-view__chip algorithm-story-view__chip--success">
                  {node}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="algorithm-story-view__section">
          <div className="algorithm-story-view__label">{tx('Returned Values')}</div>
          {Object.keys(returnedValues).length > 0 ? (
            <div className="algorithm-story-view__chips">
              {Object.entries(returnedValues).map(([key, value]) => (
                <span key={key} className="algorithm-story-view__chip algorithm-story-view__chip--success">
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          ) : (
            <span className="algorithm-story-view__empty">{tx('none yet')}</span>
          )}
        </div>
      </div>
    </div>
  );
}
