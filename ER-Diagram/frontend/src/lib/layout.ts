// frontend/src/lib/layout.ts
// Dagre-based hierarchical layout engine for ER diagrams.
// Positions parent tables above children, groups related tables,
// and places standalone tables in a grid below the hierarchy.

import type { Node, Edge } from '@xyflow/react'
import dagre from '@dagrejs/dagre'

// Layout dimension constants (match table-node component styling)
export const NODE_WIDTH = 350
const ROW_HEIGHT = 28
const HEADER_HEIGHT = 36
const PADDING = 16
const MIN_HEIGHT = 100
const MAX_HEIGHT = 320

/**
 * Extract column count from a node's data (handles generic Node typing).
 */
function getColumnCount(node: Node): number {
  const data = node.data as Record<string, unknown>
  const columns = data.columns
  return Array.isArray(columns) ? columns.length : 5
}

/**
 * Estimate the rendered height of a table node based on its column count.
 */
function estimateNodeHeight(columnCount: number): number {
  return Math.min(
    MAX_HEIGHT,
    Math.max(MIN_HEIGHT, HEADER_HEIGHT + PADDING + columnCount * ROW_HEIGHT)
  )
}

/**
 * Compute hierarchical positions for diagram nodes using dagre layout.
 *
 * - Connected nodes (those with FK edges) are arranged hierarchically
 *   with parent tables above child tables.
 * - Standalone nodes (no FK connections) are placed in a 4-column grid
 *   below the hierarchy.
 *
 * @param nodes - React Flow nodes (positions will be replaced)
 * @param edges - React Flow edges defining FK relationships
 * @param direction - Layout direction: 'TB' (top-to-bottom) or 'LR' (left-to-right)
 * @returns New array of nodes with computed positions
 */
export function getLayoutedNodes<T extends Record<string, unknown> = Record<string, unknown>>(
  nodes: Node<T>[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB'
): Node<T>[] {
  // Partition nodes into connected vs standalone
  const connectedNodeIds = new Set<string>()
  for (const edge of edges) {
    connectedNodeIds.add(edge.source)
    connectedNodeIds.add(edge.target)
  }

  const connectedNodes = nodes.filter(n => connectedNodeIds.has(n.id))
  const standaloneNodes = nodes.filter(n => !connectedNodeIds.has(n.id))

  // Layout connected nodes with dagre
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: direction,
    nodesep: 60,
    ranksep: 80,
    marginx: 50,
    marginy: 50,
  })

  for (const node of connectedNodes) {
    const height = estimateNodeHeight(getColumnCount(node))
    g.setNode(node.id, { width: NODE_WIDTH, height })
  }

  // CRITICAL: Swap edge direction so parent tables rank above children.
  // Current edges have source=FK child, target=FK parent.
  // Dagre ranks source above target, so we feed parent as dagre source.
  for (const edge of edges) {
    g.setEdge(edge.target, edge.source)
  }

  dagre.layout(g)

  // Map connected nodes to dagre-computed positions (center -> top-left)
  const layoutedConnected = connectedNodes.map(node => {
    const pos = g.node(node.id)
    const height = estimateNodeHeight(getColumnCount(node))
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - height / 2,
      },
    }
  })

  // Layout standalone nodes in grid below hierarchy
  const maxY = layoutedConnected.length > 0
    ? Math.max(
        ...layoutedConnected.map(n => {
          const height = estimateNodeHeight(getColumnCount(n))
          return n.position.y + height
        })
      )
    : 0

  const standaloneLayouted = standaloneNodes.map((node, i) => ({
    ...node,
    position: {
      x: 50 + (i % 4) * 400,
      y: maxY + 100 + Math.floor(i / 4) * 300,
    },
  }))

  return [...layoutedConnected, ...standaloneLayouted]
}
