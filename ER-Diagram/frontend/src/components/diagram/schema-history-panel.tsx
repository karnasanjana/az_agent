'use client'

import { useState, useEffect } from 'react'
import { getDiagramHistory } from '@/app/actions'
import type { SchemaChangeEntry } from '@/types/diagram'

interface SchemaHistoryPanelProps {
  isOpen: boolean
  onClose: () => void
  diagramId: string | null
}

export function SchemaHistoryPanel({ isOpen, onClose, diagramId }: SchemaHistoryPanelProps) {
  const [history, setHistory] = useState<SchemaChangeEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null)

  useEffect(() => {
    if (!isOpen || !diagramId) return
    setIsLoading(true)
    getDiagramHistory(diagramId)
      .then((data) => {
        setHistory((data.history || []) as SchemaChangeEntry[])
      })
      .catch(() => setHistory([]))
      .finally(() => setIsLoading(false))
  }, [isOpen, diagramId])

  if (!isOpen) return null

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-[440px] z-50 glass-panel bg-slate-900/95 border-l border-slate-700 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-200">Schema Changes</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {history.length} change{history.length !== 1 ? 's' : ''} tracked
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-indigo-500 border-t-transparent" />
            </div>
          )}

          {!isLoading && !diagramId && (
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-slate-700 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm text-slate-500">Save the diagram first to start tracking changes.</p>
            </div>
          )}

          {!isLoading && diagramId && history.length === 0 && (
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-slate-700 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-sm text-slate-500">No schema changes detected yet.</p>
              <p className="text-xs text-slate-600 mt-1">Changes are tracked each time you save after modifying the schema.</p>
            </div>
          )}

          {!isLoading && history.length > 0 && (
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-[11px] top-2 bottom-2 w-px bg-slate-700/50" />

              <div className="space-y-4">
                {[...history].reverse().map((entry) => {
                  const isExpanded = expandedVersion === entry.version
                  const date = new Date(entry.timestamp)
                  const relativeTime = getRelativeTime(date)

                  return (
                    <div key={entry.version} className="relative pl-8">
                      {/* Timeline dot */}
                      <div className="absolute left-0 top-1.5 w-[23px] h-[23px] rounded-full bg-slate-800 border-2 border-indigo-500/60 flex items-center justify-center">
                        <span className="text-[9px] font-bold text-indigo-400">
                          {entry.version}
                        </span>
                      </div>

                      <div
                        className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-3.5 cursor-pointer hover:border-indigo-500/30 transition-colors"
                        onClick={() => setExpandedVersion(isExpanded ? null : entry.version)}
                      >
                        {/* Summary row */}
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm text-slate-300 font-medium leading-snug">
                            {entry.summary}
                          </p>
                          <svg
                            className={`w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                            fill="none" stroke="currentColor" viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-1">{relativeTime}</p>

                        {/* Expanded detail */}
                        {isExpanded && (
                          <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2.5">
                            {/* Added tables */}
                            {entry.added_tables.length > 0 && (
                              <div>
                                <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">Tables Added</p>
                                {entry.added_tables.map((t) => (
                                  <span key={t} className="inline-block mr-1.5 mb-1 px-2 py-0.5 text-xs bg-emerald-900/30 text-emerald-400 border border-emerald-500/20 rounded-md">
                                    + {t}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Removed tables */}
                            {entry.removed_tables.length > 0 && (
                              <div>
                                <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Tables Removed</p>
                                {entry.removed_tables.map((t) => (
                                  <span key={t} className="inline-block mr-1.5 mb-1 px-2 py-0.5 text-xs bg-red-900/30 text-red-400 border border-red-500/20 rounded-md">
                                    - {t}
                                  </span>
                                ))}
                              </div>
                            )}

                            {/* Modified tables */}
                            {entry.modified_tables.length > 0 && (
                              <div>
                                <p className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider mb-1">Column Changes</p>
                                {entry.modified_tables.map((mod) => (
                                  <div key={mod.table} className="mb-2">
                                    <p className="text-xs font-medium text-slate-400 mb-0.5">{mod.table}</p>
                                    {mod.changes.map((change, i) => {
                                      const isAdd = change.startsWith('+')
                                      const isRemove = change.startsWith('-')
                                      const color = isAdd ? 'text-emerald-400' : isRemove ? 'text-red-400' : 'text-amber-400'
                                      return (
                                        <p key={i} className={`text-xs font-mono ml-2 ${color}`}>
                                          {change}
                                        </p>
                                      )
                                    })}
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* FK changes */}
                            {entry.added_foreign_keys.length > 0 && (
                              <div>
                                <p className="text-[10px] font-semibold text-indigo-400 uppercase tracking-wider mb-1">Relationships Added</p>
                                {entry.added_foreign_keys.map((fk) => (
                                  <span key={fk} className="inline-block mr-1.5 mb-1 px-2 py-0.5 text-xs bg-indigo-900/30 text-indigo-400 border border-indigo-500/20 rounded-md font-mono">
                                    + {fk}
                                  </span>
                                ))}
                              </div>
                            )}
                            {entry.removed_foreign_keys.length > 0 && (
                              <div>
                                <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Relationships Removed</p>
                                {entry.removed_foreign_keys.map((fk) => (
                                  <span key={fk} className="inline-block mr-1.5 mb-1 px-2 py-0.5 text-xs bg-red-900/30 text-red-400 border border-red-500/20 rounded-md font-mono">
                                    - {fk}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

function getRelativeTime(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
