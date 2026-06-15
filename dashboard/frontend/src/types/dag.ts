export type NodeStatus = 'idle' | 'active' | 'completed' | 'error';

export interface DagNodeDef {
  id: string;
  label: string;
  type: 'node' | 'subgraph' | 'transition' | 'terminal';
  subgraphRef?: string;
}

export interface DagEdgeDef {
  source: string;
  target: string;
  condition?: string;
  label?: string;
}

export interface SubgraphDef {
  label: string;
  nodes: DagNodeDef[];
  edges: DagEdgeDef[];
}

export interface DagDefinition {
  version: number;
  subgraphs: Record<string, SubgraphDef>;
}

export interface NodeState {
  status: NodeStatus;
  activatedAt?: number;
  completedAt?: number;
}

export interface EdgeState {
  traversed: boolean;
  label?: string;
}

export interface DagState {
  nodes: Record<string, NodeState>;
  edges: Record<string, EdgeState>;
  activeSubgraph: string;
}
