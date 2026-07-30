'use client'

import { useEffect, useState } from 'react'
import type { DatabaseSchema, ForeignKey } from '@/types/schema'
import type { InferredRelationship } from '@/types/diagram'
import { inferRelationships } from '@/app/actions'

interface InferRelationshipsPanelProps {
  isOpen: boolean
  onClose: () => void
  schema: DatabaseSchema | null
  onAccept: (fk: ForeignKey) => void
}

type ItemStatus = 'pending' | 'accepted' | 'rejected'

interface InferredItem extends InferredRelationship {
  status: ItemStatus
  selected: boolean
  key: string
}

function confidenceBadge(confidence: number) {
  if (confidence > 0.8) {
    return {
      label: `${Math.round(confidence * 100)}% high`,
      className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    }
  }
  if (confidence >= 0.5) {
    return {
      label: `${Math.round(confidence * 100)}% medium`,
      className: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    }
  }
  return {
    label: `${Math.round(confidence * 100)}% low`,
    className: 'bg-red-500/20 text-red-300 border-red-500/40',
  }
}

export function InferRelationshipsPanel({
  isOpen,
  onClose,
  schema,
  onAccept,
}: InferRelationshipsPanelProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<InferredItem[]>([])

  useEffect(() => {
    if (!isOpen || !schema) return
    let cancelled = false

    const run = async () => {
      setLoading(true)
      setError(null)
      setItems([])
      try {
        const data = await inferRelationships(schema) as { relationships?: InferredRelationship[] }
        if (cancelled) return
        const rels: InferredRelationship[] = data.relationships || []
        setItems(
          rels.map((r, i) => ({
            ...r,
            status: 'pending' as ItemStatus,
            selected: r.confidence > 0.8, // Pre-select high confidence by default
            key: `${r.source_schema}.${r.source_table}.${r.source_column}->${r.target_schema}.${r.target_table}.${r.target_column}#${i}`,
          }))
        )
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to infer relationships')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [isOpen, schema])

  const toggleSelect = (item: InferredItem) => {
    setItems((prev) =>
      prev.map((it) => (it.key === item.key ? { ...it, selected: !it.selected } : it))
    )
  }

  const selectAll = () => {
    setItems((prev) => prev.map((it) => (it.status === 'pending' ? { ...it, selected: true } : it)))
  }

  const selectHighConfidence = () => {
    setItems((prev) =>
      prev.map((it) =>
        it.status === 'pending' ? { ...it, selected: it.confidence > 0.8 } : it
      )
    )
  }

  const clearSelection = () => {
    setItems((prev) => prev.map((it) => ({ ...it, selected: false })))
  }

  const handleAcceptSelected = () => {
    const toAccept = items.filter((it) => it.status === 'pending' && it.selected)
    toAccept.forEach((item) => {
      const fk: ForeignKey = {
        constraint_name: `ai_fk_${item.source_table}_${item.source_column}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        source_table: item.source_table,
        source_schema: item.source_schema,
        source_columns: [item.source_column],
        target_table: item.target_table,
        target_schema: item.target_schema,
        target_columns: [item.target_column],
      }
      onAccept(fk)
    })
    setItems((prev) =>
      prev.map((it) =>
        it.status === 'pending' && it.selected ? { ...it, status: 'accepted', selected: false } : it
      )
    )
  }

  const handleRejectSelected = () => {
    setItems((prev) =>
      prev.map((it) =>
        it.status === 'pending' && it.selected ? { ...it, status: 'rejected', selected: false } : it
      )
    )
  }

  const selectedCount = items.filter((it) => it.status === 'pending' && it.selected).length
  const pendingCount = items.filter((it) => it.status === 'pending').length

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-[640px] max-h-[80vh] glass-panel bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700/80 flex-shrink-0">
          <div>
            <h2 className="text-base font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
              AI Relationship Inference
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Suggested foreign keys based on schema analysis
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-white/10 rounded-lg text-white/70 hover:text-white transition-colors"
            title="Close"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 chat-scroll">
          {loading && (
            <div className="flex items-center justify-center py-12 text-slate-400">
              <svg className="animate-spin h-5 w-5 mr-3 text-indigo-400" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" className="opacity-75" />
              </svg>
              Analyzing schema…
            </div>
          )}
          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
              {error}
            </div>
          )}
          {!loading && !error && items.length === 0 && (
            <p className="text-center text-slate-400 text-sm py-12">
              No additional relationships detected. Your schema looks well-connected.
            </p>
          )}
          {/* Selection toolbar */}
          {!loading && !error && pendingCount > 0 && (
            <div className="flex items-center justify-between gap-2 mb-3 px-3 py-2 bg-slate-800/40 border border-slate-700/60 rounded-lg">
              <span className="text-xs text-slate-400">
                <span className="text-indigo-300 font-medium">{selectedCount}</span> of {pendingCount} selected
              </span>
              <div className="flex gap-2 text-xs">
                <button
                  onClick={selectAll}
                  className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
                >
                  Select All
                </button>
                <span className="text-slate-600">·</span>
                <button
                  onClick={selectHighConfidence}
                  className="text-emerald-400 hover:text-emerald-300 font-medium transition-colors"
                >
                  High Confidence Only
                </button>
                <span className="text-slate-600">·</span>
                <button
                  onClick={clearSelection}
                  className="text-slate-400 hover:text-slate-300 font-medium transition-colors"
                >
                  Clear
                </button>
              </div>
            </div>
          )}
          <ul className="space-y-2">
            {items.map((item) => {
              const badge = confidenceBadge(item.confidence)
              const isPending = item.status === 'pending'
              return (
                <li
                  key={item.key}
                  className={`rounded-xl border p-3 transition-all ${
                    item.status === 'accepted'
                      ? 'bg-emerald-500/10 border-emerald-500/40'
                      : item.status === 'rejected'
                      ? 'bg-slate-800/40 border-slate-700/60 opacity-50'
                      : item.selected
                      ? 'bg-indigo-900/20 border-indigo-500/40'
                      : 'bg-slate-800/60 border-slate-700/80 hover:border-slate-600'
                  } ${isPending ? 'cursor-pointer' : ''}`}
                  onClick={() => isPending && toggleSelect(item)}
                >
                  <div className="flex items-start gap-3">
                    {/* Checkbox or status icon */}
                    <div className="flex-shrink-0 mt-0.5">
                      {isPending && (
                        <div
                          className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                            item.selected
                              ? 'bg-indigo-500 border-indigo-500'
                              : 'border-slate-600 hover:border-slate-500'
                          }`}
                        >
                          {item.selected && (
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          )}
                        </div>
                      )}
                      {item.status === 'accepted' && (
                        <div className="w-4 h-4 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#10b981" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </div>
                      )}
                      {item.status === 'rejected' && (
                        <div className="w-4 h-4 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                        </div>
                      )}
                    </div>
                    {/* Relationship details */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <code className="text-xs text-indigo-300">
                          {item.source_schema}.{item.source_table}.{item.source_column}
                        </code>
                        <span className="text-slate-500 text-xs">→</span>
                        <code className="text-xs text-indigo-300">
                          {item.target_schema}.{item.target_table}.{item.target_column}
                        </code>
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${badge.className}`}>
                          {badge.label}
                        </span>
                      </div>
                      {item.reason && (
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">{item.reason}</p>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        {/* Footer with bulk action buttons */}
        {!loading && !error && pendingCount > 0 && (
          <div className="flex items-center justify-between gap-3 px-5 py-3 border-t border-slate-700/80 bg-slate-900/60 flex-shrink-0">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              Done
            </button>
            <div className="flex gap-2">
              <button
                onClick={handleRejectSelected}
                disabled={selectedCount === 0}
                className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Reject Selected
              </button>
              <button
                onClick={handleAcceptSelected}
                disabled={selectedCount === 0}
                className="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-all shadow-[0_0_15px_rgba(79,70,229,0.4)] disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
              >
                Accept Selected ({selectedCount})
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
