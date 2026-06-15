import { memo } from 'react';
import { BaseEdge, getBezierPath, EdgeLabelRenderer, type Edge, type EdgeProps } from '@xyflow/react';

type DagEdgeData = {
  label?: string;
  traversed?: boolean;
};

export type DagFlowEdge = Edge<DagEdgeData, 'dagEdge'>;

function DagEdge({
  id,
  sourceX, sourceY,
  targetX, targetY,
  sourcePosition, targetPosition,
  data,
}: EdgeProps<DagFlowEdge>) {
  const traversed = data?.traversed ?? false;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: traversed ? 'var(--color-accent-green)' : 'rgba(255,255,255,0.12)',
          strokeWidth: traversed ? 2 : 1.2,
          transition: 'stroke 0.6s ease, stroke-width 0.4s ease',
        }}
      />
      {traversed && (
        <circle r="3" fill="var(--color-accent-green)" opacity="0.9">
          <animateMotion dur="2s" repeatCount="indefinite" path={edgePath} />
        </circle>
      )}
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              fontSize: 'var(--font-size-xs)',
              fontFamily: 'var(--font-mono)',
              color: traversed ? 'var(--color-accent-green)' : 'var(--color-text-secondary)',
              background: 'var(--color-bg-primary)',
              padding: '2px 8px',
              borderRadius: '4px',
              border: `1px solid ${traversed ? 'rgba(80,227,194,0.2)' : 'var(--color-border-subtle)'}`,
              pointerEvents: 'none',
              opacity: 1,
              transition: 'all 0.4s ease',
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(DagEdge);
