'use client'

import { useState } from 'react'
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps, type Edge } from '@xyflow/react'
import type { ManualRelationship } from '@/types/diagram'

interface ManualEdgeData {
  relationship: ManualRelationship
  onDelete?: (id: string) => void
  [key: string]: unknown
}

type ManualEdgeType = Edge<ManualEdgeData, 'manualRelationship'>

/**
 * Custom React Flow edge for manually-defined relationships.
 *
 * Visual differences from auto-detected RelationshipEdge:
 * - Dashed line (strokeDasharray="8 4")
 * - Gray color (#6B7280)
 * - Delete button appears on hover at midpoint
 * - No cardinality labels
 */
export function ManualEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<ManualEdgeType>) {
  const [isHovered, setIsHovered] = useState(false)

  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

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

      {/* Visible dashed edge */}
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          strokeWidth: 2,
          stroke: '#6B7280',
          strokeDasharray: '8 4',
        }}
        interactionWidth={20}
      />

      {/* Delete button at midpoint - appears on hover */}
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            opacity: isHovered ? 1 : 0,
            pointerEvents: isHovered ? 'all' : 'none',
            transition: 'opacity 0.2s ease-in-out',
          }}
          className="nodrag nopan"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation()
              data?.onDelete?.(id)
            }}
            className="w-5 h-5 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center text-xs font-bold shadow-sm cursor-pointer"
            title="Delete manual relationship"
          >
            &times;
          </button>
        </div>

        {/* Label showing "Manual" */}
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, 8px) translate(${labelX}px, ${labelY}px)`,
            opacity: isHovered ? 1 : 0,
            pointerEvents: 'none',
            transition: 'opacity 0.2s ease-in-out',
          }}
          className="nodrag nopan bg-gray-600 text-white px-1.5 py-0.5 rounded text-[10px] whitespace-nowrap"
        >
          Manual
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

/**
 * Edge type registration for React Flow.
 * Merge with existing edgeTypes: { ...edgeTypes, ...manualEdgeType }
 */
export const manualEdgeType = {
  manualRelationship: ManualEdge,
}
