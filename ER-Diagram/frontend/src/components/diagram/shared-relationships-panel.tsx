'use client'

import { useState, useMemo } from 'react'
import type { ForeignKey } from '@/types/schema'

interface SharedRelationshipsPanelProps {
  isOpen: boolean
  onClose: () => void
  foreignKeys: ForeignKey[]
}

export function SharedRelationshipsPanel({ isOpen, onClose, foreignKeys }: SharedRelationshipsPanelProps) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return foreignKeys
    const q = search.toLowerCase()
    return foreignKeys.filter(
      (fk) =>
        fk.constraint_name.toLowerCase().includes(q) ||
        fk.source_table.toLowerCase().includes(q) ||
        fk.target_table.toLowerCase().includes(q) ||
        fk.source_schema.toLowerCase().includes(q) ||
        fk.target_schema.toLowerCase().includes(q) ||
        fk.source_columns.some((c) => c.toLowerCase().includes(q)) ||
        fk.target_columns.some((c) => c.toLowerCase().includes(q))
    )
  }, [foreignKeys, search])

  // Group by source schema
  const grouped = useMemo(() => {
    const groups: Record<string, ForeignKey[]> = {}
    for (const fk of filtered) {
      const key = fk.source_schema
      if (!groups[key]) groups[key] = []
      groups[key].push(fk)
    }
    return groups
  }, [filtered])

  if (!isOpen) return null

  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />
      <div
        className="fixed top-0 right-0 h-full w-96 glass-panel bg-slate-900/95 border-l border-slate-700/80 shadow-2xl backdrop-blur-xl z-50 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/80">
          <div>
            <h2 className="text-lg font-bold text-slate-200">Relationships</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {foreignKeys.length} foreign key{foreignKeys.length !== 1 ? 's' : ''} total
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b border-slate-700/80">
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
              placeholder="Search tables, columns..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-slate-800/60 border border-slate-700/60 text-slate-200 placeholder:text-slate-600 rounded-lg focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-colors"
            />
          </div>
        </div>

        {/* Relationships list */}
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {filtered.length === 0 ? (
            <p className="text-sm text-slate-600 text-center py-8">
              {search ? 'No relationships match your search' : 'No relationships found'}
            </p>
          ) : (
            Object.entries(grouped).map(([schema, fks]) => (
              <div key={schema} className="mb-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">{schema}</span>
                  <span className="text-[10px] text-slate-600">({fks.length})</span>
                </div>
                <div className="space-y-2">
                  {fks.map((fk) => {
                    const isCrossDb = fk.source_schema !== fk.target_schema
                    return (
                      <div
                        key={fk.constraint_name}
                        className="border rounded-xl p-3 bg-slate-800/30 border-slate-700/50 hover:bg-slate-800/50 transition-colors"
                        style={{ borderLeftWidth: '3px', borderLeftColor: isCrossDb ? '#a855f7' : '#6366f1' }}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-[10px] font-mono text-slate-500 truncate" title={fk.constraint_name}>
                            {fk.constraint_name}
                          </span>
                          {isCrossDb && (
                            <span className="text-[9px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 border border-purple-500/20 rounded-full whitespace-nowrap">
                              cross-db
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs">
                          <div className="flex-1 min-w-0">
                            <span className="text-slate-200 font-medium">{fk.source_table}</span>
                            <span className="text-slate-500">.{fk.source_columns.join(', ')}</span>
                          </div>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400 flex-shrink-0">
                            <path d="M5 12h14M12 5l7 7-7 7" />
                          </svg>
                          <div className="flex-1 min-w-0 text-right">
                            <span className="text-slate-200 font-medium">{fk.target_table}</span>
                            <span className="text-slate-500">.{fk.target_columns.join(', ')}</span>
                          </div>
                        </div>
                        {isCrossDb && (
                          <div className="text-[10px] text-slate-600 mt-1">
                            {fk.source_schema} → {fk.target_schema}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  )
}
