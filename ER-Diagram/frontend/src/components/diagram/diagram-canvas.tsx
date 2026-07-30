'use client'

import { useState, useMemo, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useReactFlow,
  useViewport,
  getNodesBounds,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { tableNodeTypes } from './table-node'
import { edgeTypes } from './relationship-edge'
import { manualEdgeType } from './manual-edge'
import { TableSearch } from './table-search'
import { AddRelationshipPanel } from './add-relationship-panel'
import { getLayoutedNodes } from '@/lib/layout'
import type { TableNodeData, RelationshipEdgeData, ManualRelationship } from '@/types/diagram'

interface DiagramCanvasProps {
  initialNodes: Node<TableNodeData>[]
  initialEdges: Edge<RelationshipEdgeData>[]
  highlightedNodes?: Set<string> | null
  onEdgeHover?: (edgeId: string | null, sourceId?: string, targetId?: string) => void
  onEdgeClick?: (edgeId: string, sourceId: string, targetId: string) => void
  onPaneClick?: () => void
  /** Callback to expose current nodes (with updated positions) to parent */
  onNodesUpdate?: (nodes: Node<TableNodeData>[]) => void
  /** Incrementing counter that triggers auto-layout when changed */
  autoLayoutTrigger?: number
  /** Manual relationship edges (dashed gray) */
  manualEdges?: Edge[]
  /** Callback when user adds a manual relationship */
  onAddManualRelationship?: (relationship: ManualRelationship) => void
  /** Callback when user deletes a manual relationship */
  onDeleteManualRelationship?: (edgeId: string) => void
  /** Table info for the add-relationship panel dropdowns */
  tables?: Array<{ schema_name: string; table_name: string; columns: Array<{ name: string }> }>
}

/**
 * Hook to determine whether the MiniMap should be visible.
 * Shows minimap when diagram content exceeds the viewport dimensions.
 * Uses a 10% buffer (hysteresis) to prevent flicker at the threshold.
 */
function useShowMinimap(): boolean {
  const { getNodes } = useReactFlow()
  const { x, y, zoom } = useViewport()

  return useMemo(() => {
    const nodes = getNodes()
    if (nodes.length === 0) return false

    const bounds = getNodesBounds(nodes)

    // Approximate viewport dimensions from window
    const viewportWidth = (typeof window !== 'undefined' ? window.innerWidth : 1920) / zoom
    const viewportHeight = (typeof window !== 'undefined' ? window.innerHeight : 1080) / zoom

    // Show minimap if content exceeds viewport with 10% buffer (hysteresis to prevent flicker)
    const buffer = 1.1
    return bounds.width > viewportWidth * buffer || bounds.height > viewportHeight * buffer
  }, [getNodes, x, y, zoom])
}

/**
 * Inner component that uses React Flow hooks.
 * Must be wrapped in ReactFlowProvider.
 */
// All edge types: auto-detected + manual
const allEdgeTypes = { ...edgeTypes, ...manualEdgeType }

function DiagramCanvasInner({
  initialNodes,
  initialEdges,
  highlightedNodes,
  onEdgeHover,
  onEdgeClick,
  onPaneClick,
  onNodesUpdate,
  autoLayoutTrigger,
  manualEdges,
  onAddManualRelationship,
  onDeleteManualRelationship,
  tables,
}: DiagramCanvasProps) {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)
  const { setNodes, setEdges: setFlowEdges, getNodes, getEdges, fitView } = useReactFlow()

  // Sync when initialNodes/initialEdges change (e.g., after adding a dataset)
  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes, setNodes])

  useEffect(() => {
    setFlowEdges(initialEdges)
  }, [initialEdges, setFlowEdges])

  // Expose current nodes (with positions) to parent when they change
  useEffect(() => {
    if (onNodesUpdate) {
      onNodesUpdate(nodes as Node<TableNodeData>[])
    }
  }, [nodes, onNodesUpdate])

  // Re-layout when autoLayoutTrigger changes
  useEffect(() => {
    if (!autoLayoutTrigger) return
    const currentNodes = getNodes()
    const currentEdges = getEdges()
    const layouted = getLayoutedNodes(currentNodes, currentEdges, 'TB')
    setNodes(layouted)
    // Fit view after React Flow processes new positions
    window.requestAnimationFrame(() => {
      fitView({ padding: 0.2 })
    })
  }, [autoLayoutTrigger, getNodes, getEdges, setNodes, fitView])

  // Merge auto-detected edges with manual edges, injecting onDelete callback
  const mergedEdges: Edge[] = useMemo(() => {
    if (!manualEdges || manualEdges.length === 0) return edges as Edge[]
    const manualWithCallback: Edge[] = manualEdges.map((e) => ({
      ...e,
      data: {
        ...e.data,
        onDelete: onDeleteManualRelationship,
      },
    }))
    return [...(edges as Edge[]), ...manualWithCallback]
  }, [edges, manualEdges, onDeleteManualRelationship])

  const showMinimap = useShowMinimap()
  const [searchHighlightedNodes, setSearchHighlightedNodes] = useState<Set<string> | null>(null)

  // Apply opacity and highlight styling based on search and edge-hover state
  const activeHighlight = searchHighlightedNodes ?? highlightedNodes

  const styledNodes = useMemo(() => {
    return nodes.map((node) => {
      const isHighlighted = activeHighlight ? activeHighlight.has(node.id) : true
      const isSearchMatch = searchHighlightedNodes?.has(node.id) ?? false

      return {
        ...node,
        style: {
          ...node.style,
          opacity: isHighlighted ? 1 : 0.3,
          transition: 'opacity 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
          boxShadow: isSearchMatch ? '0 0 0 3px #3B82F6' : undefined,
          borderRadius: isSearchMatch ? '8px' : undefined,
        },
      }
    })
  }, [nodes, activeHighlight, searchHighlightedNodes])

  // Dim edges whose source/target are not in the highlighted set
  const styledEdges = useMemo(() => {
    if (!activeHighlight) return mergedEdges
    return mergedEdges.map((edge) => {
      const isConnected = activeHighlight.has(edge.source) && activeHighlight.has(edge.target)
      return {
        ...edge,
        style: {
          ...edge.style,
          opacity: isConnected ? 1 : 0.15,
          transition: 'opacity 0.2s ease-in-out',
        },
      }
    })
  }, [mergedEdges, activeHighlight])

  return (
    <ReactFlow
      nodes={styledNodes}
      edges={styledEdges as Edge<RelationshipEdgeData>[]}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={tableNodeTypes}
      edgeTypes={allEdgeTypes}
      // Edge hover handlers
      onEdgeMouseEnter={(_, edge) => {
        if (onEdgeHover) {
          onEdgeHover(edge.id, edge.source, edge.target)
        }
      }}
      onEdgeMouseLeave={() => {
        if (onEdgeHover) {
          onEdgeHover(null)
        }
      }}
      // Edge click handler (sticky highlight)
      onEdgeClick={(_, edge) => {
        if (onEdgeClick) {
          onEdgeClick(edge.id, edge.source, edge.target)
        }
      }}
      // Pane click handler (clear sticky highlight)
      onPaneClick={() => {
        if (onPaneClick) {
          onPaneClick()
        }
      }}
      // Snap to grid for tidy alignment
      snapToGrid={true}
      snapGrid={[20, 20]}
      // Zoom limits
      minZoom={0.1}
      maxZoom={2.0}
      // Mouse wheel zooms; click-and-drag still pans the infinite canvas
      zoomOnScroll={true}
      panOnScroll={false}
      panOnDrag={true}
      // Fit view to show all nodes initially
      fitView
      fitViewOptions={{
        padding: 0.2,
        maxZoom: 1.5,
      }}
      // Keep React Flow attribution (per plan)
      proOptions={{ hideAttribution: false }}
      // Deep dark background via class
      className="bg-slate-950"
    >
      {/* No grid background - plain white as per user decision */}
      <Background color="transparent" gap={0} />
      {/* Zoom +/-, fit view, and interactive lock controls */}
      <Controls
        showZoom={true}
        showFitView={true}
        showInteractive={true}
        position="bottom-left"
      />
      {/* Table search in top-right corner */}
      <Panel position="top-right" className="!m-2">
        <TableSearch onSearchResults={setSearchHighlightedNodes} />
      </Panel>
      {/* Add relationship panel */}
      {onAddManualRelationship && tables && tables.length > 0 && (
        <AddRelationshipPanel tables={tables} onAdd={onAddManualRelationship} />
      )}
      {/* Minimap */}
      <MiniMap
          className="rounded-xl overflow-hidden shadow-2xl backdrop-blur-md border border-slate-700/80"
          nodeColor={() => '#4f46e5'}
          nodeBorderRadius={4}
          zoomable
          pannable
          position="bottom-right"
          style={{ 
            background: 'rgba(15, 23, 42, 0.7)', 
            marginBottom: '70px',
            right: '24px'
          }}
          maskColor="rgba(0,0,0, 0.5)"
        />
    </ReactFlow>
  )
}

/**
 * DiagramCanvas - React Flow canvas wrapper with snap-to-grid and edge hover highlighting.
 *
 * Features:
 * - Plain white background
 * - Snap to grid (20px grid)
 * - Infinite canvas (pan in any direction)
 * - Fit view on load
 * - Edge hover highlighting (connected tables bright, others dimmed)
 *
 * @param initialNodes - Table nodes to render
 * @param initialEdges - Relationship edges between tables
 * @param highlightedNodes - Set of node IDs to highlight (null = all normal)
 * @param onEdgeHover - Callback when edge is hovered/unhovered
 */
export function DiagramCanvas({
  initialNodes,
  initialEdges,
  highlightedNodes,
  onEdgeHover,
  onEdgeClick,
  onPaneClick,
  onNodesUpdate,
  autoLayoutTrigger,
  manualEdges,
  onAddManualRelationship,
  onDeleteManualRelationship,
  tables,
}: DiagramCanvasProps) {
  return (
    <ReactFlowProvider>
      <DiagramCanvasInner
        initialNodes={initialNodes}
        initialEdges={initialEdges}
        highlightedNodes={highlightedNodes}
        onEdgeHover={onEdgeHover}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        onNodesUpdate={onNodesUpdate}
        autoLayoutTrigger={autoLayoutTrigger}
        manualEdges={manualEdges}
        onAddManualRelationship={onAddManualRelationship}
        onDeleteManualRelationship={onDeleteManualRelationship}
        tables={tables}
      />
    </ReactFlowProvider>
  )
}
