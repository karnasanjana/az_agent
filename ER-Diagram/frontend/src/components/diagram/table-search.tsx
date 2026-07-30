'use client'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { useReactFlow } from '@xyflow/react'
import type { TableNodeData } from '@/types/diagram'

interface TableSearchProps {
  onSearchResults?: (matchedNodeIds: Set<string> | null) => void
}

/**
 * TableSearch - Live search component for finding tables/columns on the diagram.
 *
 * Features:
 * - Live filtering with each keystroke
 * - Matches both table names and column names
 * - Pans to active match with smooth animation
 * - Keyboard navigation (ArrowUp/Down to cycle, Escape to clear)
 * - Results count display
 *
 * Must be rendered as a child of ReactFlowProvider.
 */
export function TableSearch({ onSearchResults }: TableSearchProps) {
  const { getNodes, setCenter } = useReactFlow()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)

  const matches = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase()
    return getNodes().filter((node) => {
      const data = node.data as TableNodeData
      // Match table name
      if (data.table_name.toLowerCase().includes(q)) return true
      // Match column names
      if (data.columns.some((col) => col.name.toLowerCase().includes(q))) return true
      return false
    })
  }, [query, getNodes])

  // Reset activeIndex when query changes
  useEffect(() => {
    setActiveIndex(0)
  }, [query])

  // Notify parent of matched node IDs
  useEffect(() => {
    if (matches.length > 0) {
      onSearchResults?.(new Set(matches.map((m) => m.id)))
    } else if (query.trim()) {
      // Query exists but no matches - still signal search is active with empty set
      onSearchResults?.(new Set())
    } else {
      // No query - clear search highlights
      onSearchResults?.(null)
    }
  }, [matches, query, onSearchResults])

  // Pan to active match
  useEffect(() => {
    if (matches.length > 0 && activeIndex < matches.length) {
      const node = matches[activeIndex]
      // Center on node: 175 = half of 350px node width, 100 = approximate half-height
      setCenter(node.position.x + 175, node.position.y + 100, {
        zoom: 1.2,
        duration: 500,
      })
    }
  }, [matches, activeIndex, setCenter])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (matches.length === 0) return

      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        e.preventDefault()
        setActiveIndex((prev) => (prev + 1) % matches.length)
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIndex((prev) => (prev - 1 + matches.length) % matches.length)
      } else if (e.key === 'Escape') {
        setQuery('')
      }
    },
    [matches.length]
  )

  const clearSearch = useCallback(() => {
    setQuery('')
  }, [])

  return (
    <div className="flex flex-col gap-1">
      <div className="relative">
        {/* Search icon */}
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 pointer-events-none"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={2}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
          />
        </svg>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search tables or columns..."
          className="bg-slate-900/60 backdrop-blur-md border border-slate-700 rounded-lg shadow-md pl-8 pr-8 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 text-slate-200 placeholder-slate-500 transition-all"
        />

        {/* Clear button */}
        {query && (
          <button
            onClick={clearSearch}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            aria-label="Clear search"
          >
            <svg
              className="h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Results info */}
      {query.trim() && (
        <div className="text-xs text-slate-400 px-1">
          {matches.length > 0 ? (
            <span>
              {activeIndex + 1} of {matches.length} match
              {matches.length !== 1 ? 'es' : ''}
            </span>
          ) : (
            <span>No tables or columns found</span>
          )}
        </div>
      )}
    </div>
  )
}
