import { useEffect, useState, useRef } from 'react';
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import DagNode from './DagNode';
import DagEdge from './DagEdge';
import { DagDefinition, DagState } from '../types/dag';
import { layoutTopLevel, layoutSubgraph } from '../utils/layoutAllSubgraphs';

const nodeTypes = { dagNode: DagNode };
const edgeTypes = { dagEdge: DagEdge };

interface DagViewProps {
  dagState: DagState;
  mode: 'live' | 'replay' | 'idle';
  definition: DagDefinition | null;
  onDefinitionLoaded?: (def: DagDefinition) => void;
}

const SUBGRAPH_PHASE_MAP: Record<string, string> = {
  codegen_phase: 'codegen',
  hacker_phase: 'hacker',
};

function computeMetrics(nodeId: string, status: string): string {
  if (nodeId === 'codegen_phase' && status === 'active') return 'Running';
  if (nodeId === 'hacker_phase' && status === 'active') return 'Running';
  return '';
}

function DagViewInner({ dagState, mode, definition, onDefinitionLoaded }: DagViewProps) {
  const [localDef, setLocalDef] = useState<DagDefinition | null>(definition);
  const [activeView, setActiveView] = useState<string>('top');
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [transitioning, setTransitioning] = useState(false);
  const autoFollowRef = useRef(true);
  const lastActiveRef = useRef<string | null>(null);
  const { fitView, fitBounds, getNodes } = useReactFlow();

  useEffect(() => {
    if (definition) {
      setLocalDef(definition);
      return;
    }
    fetch('/api/dag')
      .then((r) => r.json())
      .then((d: DagDefinition) => {
        setLocalDef(d);
        onDefinitionLoaded?.(d);
      })
      .catch(() => {});
  }, [definition, onDefinitionLoaded]);

  useEffect(() => {
    if (!localDef) return;
    setTransitioning(true);
    const timer = setTimeout(() => {
      let layout;
      if (activeView === 'top') {
        layout = layoutTopLevel(localDef);
      } else {
        layout = layoutSubgraph(localDef, activeView);
      }
      setNodes(layout.nodes as Node[]);
      setEdges(layout.edges as Edge[]);
      setTimeout(() => {
        fitView({ duration: 300 });
        setTransitioning(false);
      }, 50);
    }, 150);
    return () => clearTimeout(timer);
  }, [localDef, activeView, setNodes, setEdges, fitView]);

  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.type !== 'dagNode') return n;
        const data = n.data as Record<string, unknown>;
        const subgraph = data.subgraph as string;
        const originalId = data.originalId as string;
        const key = subgraph && subgraph !== 'top' ? `${subgraph}/${originalId}` : originalId;
        const nodeState = dagState.nodes[key] || dagState.nodes[originalId];
        const status = nodeState?.status || 'idle';
        const metrics = subgraph === 'top' ? computeMetrics(originalId, status) : '';
        return {
          ...n,
          data: { ...data, status, metrics },
        };
      })
    );
  }, [dagState.nodes, setNodes]);

  // Auto-drill-down
  useEffect(() => {
    if (mode === 'idle' || !autoFollowRef.current || !localDef) return;

    const activeSubgraphNode = Object.entries(dagState.nodes).find(([key, v]) => {
      if (v.status !== 'active') return false;
      return key in SUBGRAPH_PHASE_MAP;
    });

    if (activeSubgraphNode) {
      const [key] = activeSubgraphNode;
      const subId = SUBGRAPH_PHASE_MAP[key];
      if (subId && activeView !== subId) {
        setActiveView(subId);
      }
    } else if (activeView !== 'top') {
      const anySubActive = Object.entries(dagState.nodes).some(
        ([k, v]) => v.status === 'active' && k.startsWith(`${activeView}/`)
      );
      if (!anySubActive) {
        setActiveView('top');
      }
    }
  }, [dagState.nodes, mode, localDef, activeView]);

  // Auto-focus on active node in sub-view
  useEffect(() => {
    if (activeView === 'top') return;
    const activeKey = Object.entries(dagState.nodes).find(
      ([k, v]) => v.status === 'active' && k.startsWith(`${activeView}/`)
    )?.[0];
    if (!activeKey || activeKey === lastActiveRef.current) return;
    lastActiveRef.current = activeKey;

    const allNodes = getNodes();
    const activeNode = allNodes.find((n) => n.id === activeKey);
    if (activeNode && activeNode.measured?.width && activeNode.measured?.height) {
      fitBounds(
        {
          x: activeNode.position.x - 150,
          y: activeNode.position.y - 100,
          width: (activeNode.measured.width || 220) + 300,
          height: (activeNode.measured.height || 64) + 200,
        },
        { duration: 400 }
      );
    }
  }, [dagState.nodes, activeView, getNodes, fitBounds]);

  useEffect(() => {
    setEdges((eds) =>
      eds.map((e) => {
        const edgeState = dagState.edges[e.id];
        if (!edgeState) return e;
        return {
          ...e,
          data: { ...(e.data as object), traversed: edgeState.traversed },
        };
      })
    );
  }, [dagState.edges, setEdges]);

  const handleNodeClick = (_event: React.MouseEvent, node: Node) => {
    const data = node.data as Record<string, unknown>;
    if (data.expandable && data.subgraphRef) {
      autoFollowRef.current = false;
      setActiveView(data.subgraphRef as string);
    }
  };

  const handleBackToTop = () => {
    autoFollowRef.current = true;
    setActiveView('top');
  };

  const subLabel = activeView !== 'top' && localDef?.subgraphs[activeView]
    ? localDef.subgraphs[activeView].label
    : '';

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* Breadcrumb */}
      <div className="dag-view__breadcrumb">
        <span
          className={`dag-view__crumb ${activeView === 'top' ? 'dag-view__crumb--active' : 'dag-view__crumb--link'}`}
          onClick={activeView !== 'top' ? handleBackToTop : undefined}
        >
          Overview
        </span>
        {activeView !== 'top' && (
          <>
            <span className="dag-view__crumb-sep">›</span>
            <span className="dag-view__crumb dag-view__crumb--active">{subLabel}</span>
          </>
        )}
      </div>

      <div className={`dag-view__canvas ${transitioning ? 'dag-view__canvas--fade' : ''}`}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodeClick={handleNodeClick}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
          maxZoom={2}
        >
          <Background color="rgba(255,255,255,0.03)" gap={30} size={1} />
          <Controls position="bottom-left" />
          <MiniMap
            position="bottom-right"
            nodeColor={(n) => {
              const status = (n.data as Record<string, unknown>)?.status as string;
              if (status === 'active') return '#0070f3';
              if (status === 'completed') return '#50e3c2';
              if (status === 'error') return '#ee5253';
              return 'rgba(255,255,255,0.1)';
            }}
            maskColor="rgba(0,0,0,0.7)"
            style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10 }}
          />
        </ReactFlow>
      </div>

      <style>{`
        .dag-view__breadcrumb {
          position: absolute;
          top: 14px;
          left: 16px;
          z-index: 10;
          display: flex;
          align-items: center;
          gap: 6px;
          background: var(--color-bg-glass);
          backdrop-filter: blur(12px);
          border: 1px solid var(--color-border-glass);
          border-radius: var(--radius-sm);
          padding: 8px 16px;
        }
        .dag-view__crumb {
          font-size: var(--font-size-sm);
          font-weight: 500;
        }
        .dag-view__crumb--link {
          color: var(--color-accent-blue);
          cursor: pointer;
          transition: opacity var(--transition-fast);
        }
        .dag-view__crumb--link:hover {
          opacity: 0.8;
        }
        .dag-view__crumb--active {
          color: var(--color-text-primary);
        }
        .dag-view__crumb-sep {
          color: var(--color-text-muted);
          font-size: var(--font-size-sm);
        }
        .dag-view__canvas {
          width: 100%;
          height: 100%;
          transition: opacity 0.15s ease;
        }
        .dag-view__canvas--fade {
          opacity: 0.3;
        }
      `}</style>
    </div>
  );
}

export default function DagView(props: DagViewProps) {
  return (
    <ReactFlowProvider>
      <DagViewInner {...props} />
    </ReactFlowProvider>
  );
}
