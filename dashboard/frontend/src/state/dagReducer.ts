import { DagState, NodeStatus } from '../types/dag';
import { DagDefinition } from '../types/dag';
import { AlgoPilotEvent } from '../types/events';

export const initialDagState: DagState = {
  nodes: {},
  edges: {},
  activeSubgraph: 'top',
};

function nodeKey(subgraph: string, nodeId: string): string {
  if (subgraph === 'top') return nodeId;
  return `${subgraph}/${nodeId}`;
}

function edgeId(subgraph: string, source: string, target: string): string {
  return `${subgraph}/${source}->${target}`;
}

export function createDagReducer(definition: DagDefinition | null) {
  return function dagReducer(state: DagState, event: AlgoPilotEvent): DagState {
    switch (event.type) {
      case 'solve_start':
        return { ...initialDagState };

      case 'node_enter': {
        const { node_id, subgraph } = event as { node_id: string; subgraph: string; type: string; ts: number; seq: number };
        const key = nodeKey(subgraph, node_id);
        return {
          ...state,
          activeSubgraph: subgraph || state.activeSubgraph,
          nodes: {
            ...state.nodes,
            [key]: { status: 'active' as NodeStatus, activatedAt: event.ts },
          },
        };
      }

      case 'node_exit': {
        const { node_id, subgraph, routing_decision } = event as { node_id: string; subgraph: string; routing_decision: string; type: string; ts: number; seq: number };
        const key = nodeKey(subgraph, node_id);
        const prev = state.nodes[key];
        const newNodes = {
          ...state.nodes,
          [key]: { ...prev, status: 'completed' as NodeStatus, completedAt: event.ts },
        };

        const newEdges = { ...state.edges };
        if (definition) {
          const sub = definition.subgraphs[subgraph];
          if (sub) {
            const outgoing = sub.edges.filter(e => e.source === node_id && e.target !== 'END');
            for (const e of outgoing) {
              if (outgoing.length === 1 || !e.label || e.label === routing_decision) {
                const eid = edgeId(subgraph, e.source, e.target);
                newEdges[eid] = { traversed: true, label: e.label };
              }
            }
          }
        }

        return { ...state, nodes: newNodes, edges: newEdges, activeSubgraph: subgraph || state.activeSubgraph };
      }

      case 'phase_start': {
        const { phase } = event as { phase: string; type: string; ts: number; seq: number };
        const phaseNodeMap: Record<string, string> = {
          abstract_phase: 'abstract_phase',
          testgen_phase: 'testgen_phase',
          codegen_phase: 'codegen_phase',
          hacker_phase: 'hacker_phase',
        };
        const nodeId = phaseNodeMap[phase];
        if (!nodeId) return state;
        return {
          ...state,
          nodes: {
            ...state.nodes,
            [nodeId]: { status: 'active' as NodeStatus, activatedAt: event.ts },
          },
        };
      }

      case 'phase_done': {
        const { phase } = event as { phase: string; type: string; ts: number; seq: number; data: Record<string, unknown> };
        const phaseNodeMap: Record<string, string> = {
          abstract_phase: 'abstract_phase',
          testgen_phase: 'testgen_phase',
          codegen_phase: 'codegen_phase',
          hacker_phase: 'hacker_phase',
        };
        const nodeId = phaseNodeMap[phase];
        if (!nodeId) return state;
        const prev = state.nodes[nodeId];
        return {
          ...state,
          nodes: {
            ...state.nodes,
            [nodeId]: { ...prev, status: 'completed' as NodeStatus, completedAt: event.ts },
          },
        };
      }

      default:
        return state;
    }
  };
}

export { edgeId, nodeKey };
