import dagre from 'dagre';
import { DagDefinition } from '../types/dag';

export interface LayoutNode {
  id: string;
  type: 'dagNode';
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface LayoutEdge {
  id: string;
  source: string;
  target: string;
  type: 'dagEdge';
  data: { label: string; traversed: boolean };
}

const TOP_NODE_WIDTH = 280;
const TOP_NODE_HEIGHT = 80;
const SUB_NODE_WIDTH = 220;
const SUB_NODE_HEIGHT = 64;

export function layoutTopLevel(definition: DagDefinition): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  const top = definition.subgraphs['top'];
  if (!top) return { nodes: [], edges: [] };

  const transitionIds = new Set(top.nodes.filter(n => n.type === 'transition').map(n => n.id));
  const realNodes = top.nodes.filter(n => n.id !== 'END' && !transitionIds.has(n.id));

  const mergedEdges: { source: string; target: string; label: string }[] = [];
  for (const e of top.edges) {
    if (e.target === 'END' || e.source === 'END') continue;
    if (transitionIds.has(e.target)) {
      const outgoing = top.edges.filter(oe => oe.source === e.target && oe.target !== 'END');
      for (const oe of outgoing) {
        if (transitionIds.has(oe.target)) continue;
        mergedEdges.push({ source: e.source, target: oe.target, label: oe.label || '' });
      }
    } else if (!transitionIds.has(e.source)) {
      mergedEdges.push({ source: e.source, target: e.target, label: e.label || '' });
    }
  }

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 100, ranksep: 120 });

  for (const n of realNodes) {
    g.setNode(n.id, { width: TOP_NODE_WIDTH, height: TOP_NODE_HEIGHT });
  }
  for (const e of mergedEdges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);

  const nodes: LayoutNode[] = [];
  const edges: LayoutEdge[] = [];

  for (const n of realNodes) {
    const pos = g.node(n.id);
    if (!pos) continue;
    nodes.push({
      id: n.id,
      type: 'dagNode',
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        label: n.label,
        nodeType: n.type,
        status: 'idle',
        subgraph: 'top',
        originalId: n.id,
        handleDir: 'TB',
        expandable: n.type === 'subgraph',
        subgraphRef: n.subgraphRef || null,
        level: 'top',
      },
    });
  }

  for (const e of mergedEdges) {
    if (!g.hasNode(e.source) || !g.hasNode(e.target)) continue;
    edges.push({
      id: `top/${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      type: 'dagEdge',
      data: { label: e.label, traversed: false },
    });
  }

  return { nodes, edges };
}

export function layoutSubgraph(definition: DagDefinition, subId: string): { nodes: LayoutNode[]; edges: LayoutEdge[] } {
  const sub = definition.subgraphs[subId];
  if (!sub) return { nodes: [], edges: [] };

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 70, ranksep: 90 });

  for (const n of sub.nodes) {
    if (n.id === 'END') continue;
    g.setNode(n.id, { width: SUB_NODE_WIDTH, height: SUB_NODE_HEIGHT });
  }
  for (const e of sub.edges) {
    if (e.target === 'END' || e.source === 'END') continue;
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);

  const nodes: LayoutNode[] = [];
  const edges: LayoutEdge[] = [];

  for (const n of sub.nodes) {
    if (n.id === 'END') continue;
    const pos = g.node(n.id);
    if (!pos) continue;
    nodes.push({
      id: `${subId}/${n.id}`,
      type: 'dagNode',
      position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
      data: {
        label: n.label,
        nodeType: n.type,
        status: 'idle',
        subgraph: subId,
        originalId: n.id,
        handleDir: 'TB',
        expandable: false,
        subgraphRef: null,
        level: 'sub',
      },
    });
  }

  for (const e of sub.edges) {
    if (e.target === 'END' || e.source === 'END') continue;
    if (!g.hasNode(e.source) || !g.hasNode(e.target)) continue;
    edges.push({
      id: `${subId}/${e.source}->${e.target}`,
      source: `${subId}/${e.source}`,
      target: `${subId}/${e.target}`,
      type: 'dagEdge',
      data: { label: e.label || '', traversed: false },
    });
  }

  return { nodes, edges };
}
