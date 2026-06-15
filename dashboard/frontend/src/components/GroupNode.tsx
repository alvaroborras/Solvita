import { memo } from 'react';
import { type Node, type NodeProps, Handle, Position } from '@xyflow/react';

type GroupNodeData = {
  label: string;
  subgraphRef: string;
};

export type GroupFlowNode = Node<GroupNodeData, 'groupNode'>;

function GroupNode({ data }: NodeProps<GroupFlowNode>) {
  return (
    <div className="group-node">
      <div className="group-node__label">{data.label}</div>
      <Handle type="target" position={Position.Left} className="group-node__handle" />
      <Handle type="source" position={Position.Right} className="group-node__handle" />

      <style>{`
        .group-node {
          width: 100%;
          height: 100%;
          background: rgba(255, 255, 255, 0.015);
          border: 1px dashed rgba(255, 255, 255, 0.08);
          border-radius: var(--radius-lg);
          position: relative;
        }
        .group-node__label {
          position: absolute;
          top: 10px;
          left: 16px;
          font-size: 12px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--color-text-muted);
          background: var(--color-bg-primary);
          padding: 2px 8px;
          border-radius: 4px;
          border: 1px solid var(--color-border-subtle);
        }
        .group-node__handle {
          background: transparent !important;
          border: none !important;
          width: 1px !important;
          height: 1px !important;
        }
      `}</style>
    </div>
  );
}

export default memo(GroupNode);
