import { memo } from 'react';
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { NodeStatus } from '../types/dag';

type DagNodeData = {
  label: string;
  nodeType: string;
  status: NodeStatus;
  subgraph?: string;
  originalId?: string;
  handleDir?: 'LR' | 'TB';
  expandable?: boolean;
  subgraphRef?: string | null;
  level?: 'top' | 'sub';
  metrics?: string;
};

export type DagFlowNode = Node<DagNodeData, 'dagNode'>;

function DagNode({ data }: NodeProps<DagFlowNode>) {
  const status = data.status || 'idle';
  const isTerminal = data.nodeType === 'terminal';
  const isExpandable = data.expandable;
  const isTop = data.level === 'top';
  const targetPos = data.handleDir === 'LR' ? Position.Left : Position.Top;
  const sourcePos = data.handleDir === 'LR' ? Position.Right : Position.Bottom;

  const className = [
    'dag-node',
    isTop ? 'dag-node--top' : 'dag-node--sub',
    isTerminal ? 'dag-node--terminal' : '',
    isExpandable ? 'dag-node--expandable' : '',
    `dag-node--${status}`,
  ].filter(Boolean).join(' ');

  return (
    <div className={className}>
      <Handle type="target" position={targetPos} className="dag-node__handle" />
      <span className="dag-node__label">{data.label}</span>
      {data.metrics && <span className={`dag-node__metrics dag-node__metrics--${status}`}>{data.metrics}</span>}
      {isExpandable && !data.metrics && <span className="dag-node__expand-hint">click to expand</span>}
      <Handle type="source" position={sourcePos} className="dag-node__handle" />
      <style>{nodeStyles}</style>
    </div>
  );
}

const nodeStyles = `
  .dag-node {
    transition: all var(--transition-normal);
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }

  /* Top-level modules — large and prominent */
  .dag-node--top {
    padding: 20px 36px;
    min-width: 260px;
    min-height: 70px;
    text-align: center;
    background: var(--color-bg-glass);
    backdrop-filter: blur(8px);
    border: 2px solid var(--color-border-glass);
    border-radius: var(--radius-lg);
  }
  .dag-node--top .dag-node__label {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text-primary);
    white-space: nowrap;
  }

  /* Sub-level nodes — slightly smaller */
  .dag-node--sub {
    padding: 16px 28px;
    min-width: 200px;
    min-height: 56px;
    text-align: center;
    background: var(--color-bg-glass);
    backdrop-filter: blur(8px);
    border: 1.5px solid var(--color-border-glass);
    border-radius: var(--radius-md);
  }
  .dag-node--sub .dag-node__label {
    font-size: 15px;
    font-weight: 500;
    color: var(--color-text-primary);
    white-space: nowrap;
  }

  .dag-node--terminal {
    border-radius: var(--radius-pill);
  }

  .dag-node--expandable {
    cursor: pointer;
    border-style: solid;
  }
  .dag-node--expandable:hover {
    border-color: var(--color-border-hover);
    background: var(--color-bg-elevated);
    transform: scale(1.02);
  }

  .dag-node__expand-hint {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-top: 4px;
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .dag-node--expandable:hover .dag-node__expand-hint {
    opacity: 1;
  }

  .dag-node__metrics {
    font-size: 13px;
    font-family: var(--font-mono);
    font-weight: 500;
    margin-top: 4px;
    letter-spacing: -0.01em;
  }
  .dag-node__metrics--active {
    color: var(--color-accent-blue);
  }
  .dag-node__metrics--completed {
    color: var(--color-accent-green);
  }
  .dag-node__metrics--idle {
    color: var(--color-text-muted);
  }

  .dag-node__handle {
    background: rgba(255,255,255,0.15) !important;
    border: none !important;
    width: 8px !important;
    height: 8px !important;
  }

  /* Status: active — blue pulse */
  .dag-node--active.dag-node--top,
  .dag-node--active.dag-node--sub {
    border-color: var(--color-accent-blue);
    box-shadow: 0 0 36px var(--color-accent-blue-glow), inset 0 0 20px rgba(0, 112, 243, 0.06);
    transform: scale(1.03);
    animation: pulse-active 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  }

  /* Status: completed — green fill */
  .dag-node--completed.dag-node--top,
  .dag-node--completed.dag-node--sub {
    border-color: var(--color-accent-green);
    background: rgba(80, 227, 194, 0.10);
    box-shadow: 0 0 20px var(--color-accent-green-glow);
  }
  .dag-node--completed .dag-node__label {
    color: var(--color-accent-green);
  }

  /* Status: error — red pulse */
  .dag-node--error.dag-node--top,
  .dag-node--error.dag-node--sub {
    border-color: var(--color-accent-red);
    box-shadow: 0 0 24px var(--color-accent-red-glow);
    animation: pulse-error 1.5s ease-in-out infinite;
  }
  .dag-node--error .dag-node__label {
    color: var(--color-accent-red);
  }
`;

export default memo(DagNode);
