'use client'

import { useState, useMemo } from 'react'
import type { ForeignKey } from '@/types/schema'
import type { ManualRelationship } from '@/types/diagram'

interface RelationshipsPanelProps {
  isOpen: boolean
  onClose: () => void
  autoRelationships: ForeignKey[]
  manualRelationships: ManualRelationship[]
  onDeleteManual: (id: string) => void
  onDeleteAuto: (constraintName: string) => void
  onClearAllManual: () => void
  onHighlightEdge: (sourceId: string, targetId: string) => void
  onClearHighlight: () => void
}

export function RelationshipsPanel({
  isOpen,
  onClose,
  autoRelationships,
  manualRelationships,
  onDeleteManual,
  onDeleteAuto,
  onClearAllManual,
  onHighlightEdge,
  onClearHighlight,
}: RelationshipsPanelProps) {
  const [search, setSearch] = useState('')
  const [autoExpanded, setAutoExpanded] = useState(true)
  const [manualExpanded, setManualExpanded] = useState(true)
  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const [stickyHighlight, setStickyHighlight] = useState<string | null>(null)

  const totalCount = autoRelationships.length + manualRelationships.length

  const filteredAuto = useMemo(() => {
    if (!search.trim()) return autoRelationships
    const q = search.toLowerCase()
    return autoRelationships.filter(
      (fk) =>
        fk.constraint_name.toLowerCase().includes(q) ||
        fk.source_table.toLowerCase().includes(q) ||
        fk.target_table.toLowerCase().includes(q) ||
        fk.source_columns.some((c) => c.toLowerCase().includes(q)) ||
        fk.target_columns.some((c) => c.toLowerCase().includes(q))
    )
  }, [autoRelationships, search])

  const filteredManual = useMemo(() => {
    if (!search.trim()) return manualRelationships
    const q = search.toLowerCase()
    return manualRelationships.filter(
      (r) =>
        r.source_table.toLowerCase().includes(q) ||
        r.target_table.toLowerCase().includes(q) ||
        r.source_column.toLowerCase().includes(q) ||
        r.target_column.toLowerCase().includes(q)
    )
  }, [manualRelationships, search])

  const handleCardMouseEnter = (sourceId: string, targetId: string) => {
    if (!stickyHighlight) {
      onHighlightEdge(sourceId, targetId)
    }
  }

  const handleCardMouseLeave = () => {
    if (!stickyHighlight) {
      onClearHighlight()
    }
  }

  const handleCardClick = (key: string, sourceId: string, targetId: string) => {
    if (stickyHighlight === key) {
      setStickyHighlight(null)
      onClearHighlight()
    } else {
      setStickyHighlight(key)
      onHighlightEdge(sourceId, targetId)
    }
  }

  const handleBackdropClick = () => {
    setStickyHighlight(null)
    onClearHighlight()
    onClose()
  }

  const handleClearAll = () => {
    onClearAllManual()
    setConfirmClearAll(false)
  }

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={handleBackdropClick}
      />

      {/* Panel */}
      <div
        className="fixed top-0 right-0 h-full w-80 glass-panel bg-slate-900/95 border-l border-slate-700/80 shadow-2xl backdrop-blur-xl z-50 flex flex-col animate-slide-in-right"
        style={{
          animation: 'slideInRight 0.2s ease-out',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/80 bg-slate-900/50">
          <h2 className="text-lg font-semibold text-slate-200">
            Relationships ({totalCount})
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded transition-colors"
            aria-label="Close panel"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-4 py-3 border-b border-slate-700/80">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search relationships..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-slate-900/60 border border-slate-700 text-slate-200 placeholder:text-slate-500 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto">
          {/* Auto-detected section */}
          <div className="border-b border-slate-700/80">
            <button
              onClick={() => setAutoExpanded(!autoExpanded)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-800/50 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <svg
                  className={`w-3 h-3 text-slate-500 transition-transform ${autoExpanded ? 'rotate-90' : ''}`}
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M8 5v14l11-7z" />
                </svg>
                Auto-detected ({filteredAuto.length})
              </span>
            </button>

            {autoExpanded && (
              <div className="px-4 pb-3 space-y-2">
                {filteredAuto.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No auto-detected relationships</p>
                ) : (
                  filteredAuto.map((fk) => {
                    const sourceNodeId = `${fk.source_schema}.${fk.source_table}`
                    const targetNodeId = `${fk.target_schema}.${fk.target_table}`
                    const cardKey = `auto-${fk.constraint_name}`
                    return (
                      <div
                        key={cardKey}
                        className={`border rounded-lg p-2.5 text-xs cursor-pointer transition-colors ${
                          stickyHighlight === cardKey
                            ? 'bg-indigo-900/30 border-indigo-500 shadow-[inset_0_0_10px_rgba(79,70,229,0.1)]'
                            : 'bg-slate-900/40 border-slate-700/80 hover:bg-slate-800/80'
                        }`}
                        style={{ borderLeftWidth: '3px', borderLeftColor: '#6366f1', borderLeftStyle: 'solid' }}
                        onMouseEnter={() => handleCardMouseEnter(sourceNodeId, targetNodeId)}
                        onMouseLeave={handleCardMouseLeave}
                        onClick={() => handleCardClick(cardKey, sourceNodeId, targetNodeId)}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-slate-400 font-mono truncate" title={fk.constraint_name}>
                            {fk.constraint_name}
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteAuto(fk.constraint_name)
                            }}
                            className="ml-2 p-0.5 text-slate-500 hover:text-red-400 transition-colors flex-shrink-0"
                            title="Remove relationship"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        </div>
                        <div className="text-slate-200 font-medium">
                          {fk.source_table}
                        </div>
                        {fk.source_columns.map((col, i) => (
                          <div key={i} className="text-slate-400 pl-2">.{col}</div>
                        ))}
                        <div className="text-indigo-400 pl-2">
                          &rarr; {fk.target_table}
                        </div>
                        {fk.target_columns.map((col, i) => (
                          <div key={i} className="text-slate-400 pl-4">.{col}</div>
                        ))}
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>

          {/* Manual section */}
          <div className="border-t border-slate-700/80 mt-1 pt-1">
            <div className="flex items-center justify-between px-4 py-2.5">
              <button
                onClick={() => setManualExpanded(!manualExpanded)}
                className="flex items-center gap-1.5 text-sm font-medium text-slate-300 hover:text-slate-100 transition-colors"
              >
                <svg
                  className={`w-3 h-3 text-slate-500 transition-transform ${manualExpanded ? 'rotate-90' : ''}`}
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M8 5v14l11-7z" />
                </svg>
                Manual ({filteredManual.length})
              </button>

              {manualRelationships.length > 0 && manualExpanded && (
                <div>
                  {confirmClearAll ? (
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-red-600">
                        Delete all {manualRelationships.length}?
                      </span>
                      <button
                        onClick={handleClearAll}
                        className="text-xs text-red-600 font-medium hover:text-red-800 transition-colors px-1"
                      >
                        Yes
                      </button>
                      <button
                        onClick={() => setConfirmClearAll(false)}
                        className="text-xs text-slate-400 hover:text-slate-200 transition-colors px-1"
                      >
                        No
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setConfirmClearAll(true)}
                      className="text-xs text-red-500 hover:text-red-700 transition-colors"
                    >
                      Clear All
                    </button>
                  )}
                </div>
              )}
            </div>

            {manualExpanded && (
              <div className="px-4 pb-3 space-y-2">
                {filteredManual.length === 0 ? (
                  <p className="text-xs text-slate-500 py-2">No manual relationships added yet</p>
                ) : (
                  filteredManual.map((r) => {
                    const sourceNodeId = `${r.source_database}.${r.source_table}`
                    const targetNodeId = `${r.target_database}.${r.target_table}`
                    const cardKey = `manual-${r.id}`
                    return (
                      <div
                        key={cardKey}
                        className={`border rounded-lg p-2.5 text-xs cursor-pointer transition-colors group ${
                          stickyHighlight === cardKey
                            ? 'bg-slate-800 border-slate-500'
                            : 'bg-slate-900/40 border-slate-700/80 hover:bg-slate-800/80'
                        }`}
                        style={{ borderLeftWidth: '3px', borderLeftColor: '#94a3b8', borderLeftStyle: 'dashed' }}
                        onMouseEnter={() => handleCardMouseEnter(sourceNodeId, targetNodeId)}
                        onMouseLeave={handleCardMouseLeave}
                        onClick={() => handleCardClick(cardKey, sourceNodeId, targetNodeId)}
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="text-slate-200 font-medium">
                              {r.source_table}.{r.source_column}
                            </div>
                            <div className="text-slate-400 pl-2">
                              &rarr; {r.target_table}.{r.target_column}
                            </div>
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteManual(r.id)
                            }}
                            className="ml-2 p-0.5 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
                            aria-label="Delete relationship"
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>
        </div>
      </div>

    </>
  )
}
