'use client'

import { useState } from 'react'
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react'
import type { RelationshipEdge as RelationshipEdgeType } from '@/types/diagram'

/**
 * Custom React Flow edge for displaying foreign key relationships.
 *
 * Features:
 * - Smoothstep routing (orthogonal with rounded corners) for clean ER look
 * - Color from edge data for visual FK differentiation
 * - Wider interaction area via invisible path for easier hover
 * - Cardinality labels on hover (source label, target label, midpoint tooltip)
 *
 * Hover interaction for highlighting is handled at the canvas level via onEdgeMouseEnter/Leave.
 * Hover interaction for cardinality labels is handled internally via invisible interaction path.
 */
export function RelationshipEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
}: EdgeProps<RelationshipEdgeType>) {
  const [isHovered, setIsHovered] = useState(false)

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  // Calculate label positions near source and target ends
  // Move 8% from each end toward the midpoint for readable placement
  const sourceLabelX = sourceX + (targetX - sourceX) * 0.08
  const sourceLabelY = sourceY + (targetY - sourceY) * 0.08
  const targetLabelX = targetX + (sourceX - targetX) * 0.08
  const targetLabelY = targetY + (sourceY - targetY) * 0.08

  const cardinalityInfo = data?.cardinalityInfo

  return (
    <>
      {/* Invisible wider interaction path for hover detection */}
      <path
        d={edgePath}
        strokeWidth={40}
        stroke="transparent"
        fill="none"
        pointerEvents="stroke"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      />

      {/* Visible edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          strokeWidth: 2,
          stroke: data?.color || '#3B82F6',
        }}
        interactionWidth={20}
      />

      {/* Cardinality labels rendered via EdgeLabelRenderer (HTML overlay) */}
      {cardinalityInfo && (
        <EdgeLabelRenderer>
          {/* Source label (near child/source table) */}
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${sourceLabelX}px, ${sourceLabelY}px)`,
              opacity: isHovered ? 1 : 0,
              pointerEvents: 'none',
              transition: 'opacity 0.2s ease-in-out',
            }}
            className="nodrag nopan bg-white px-1.5 py-0.5 rounded text-xs font-semibold border border-gray-200 shadow-sm"
          >
            {cardinalityInfo.sourceLabel}
          </div>

          {/* Target label (near parent/target table) */}
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${targetLabelX}px, ${targetLabelY}px)`,
              opacity: isHovered ? 1 : 0,
              pointerEvents: 'none',
              transition: 'opacity 0.2s ease-in-out',
            }}
            className="nodrag nopan bg-white px-1.5 py-0.5 rounded text-xs font-semibold border border-gray-200 shadow-sm"
          >
            {cardinalityInfo.targetLabel}
          </div>

          {/* Tooltip at edge midpoint */}
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              opacity: isHovered ? 1 : 0,
              pointerEvents: 'none',
              transition: 'opacity 0.2s ease-in-out',
            }}
            className="nodrag nopan bg-gray-800 text-white px-2 py-1 rounded text-xs whitespace-nowrap"
          >
            {cardinalityInfo.tooltip}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

/**
 * Edge type registration for React Flow.
 * Use this in the ReactFlow edgeTypes prop.
 */
export const edgeTypes = {
  relationship: RelationshipEdge,
}
