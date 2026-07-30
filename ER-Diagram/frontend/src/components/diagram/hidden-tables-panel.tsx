'use client'

import { useState } from 'react'
import type { DatabaseSchema } from '@/types/schema'

interface HiddenTablesPanelProps {
  hiddenTables: Set<string>
  schema: DatabaseSchema | null
  onRestore: (tableId: string) => void
  onRestoreAll: () => void
}

export function HiddenTablesPanel({ hiddenTables, schema, onRestore, onRestoreAll }: HiddenTablesPanelProps) {
  const [expanded, setExpanded] = useState(false)

  if (hiddenTables.size === 0) return null

  const hiddenList = Array.from(hiddenTables).map((id) => {
    const [schemaName, tableName] = id.split('.')
    const table = schema?.tables.find(t => t.schema_name === schemaName && t.table_name === tableName)
    return {
      id,
      schemaName,
      tableName,
      columnCount: table?.columns.length ?? 0,
    }
  })

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
      {expanded ? (
        <div className="bg-slate-900/95 backdrop-blur-xl border border-slate-700 rounded-2xl shadow-2xl w-80 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/80">
            <span className="text-sm font-semibold text-slate-200">
              Hidden Tables ({hiddenTables.size})
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={onRestoreAll}
                className="text-[11px] text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
              >
                Restore All
              </button>
              <button
                onClick={() => setExpanded(false)}
                className="p-1 text-slate-500 hover:text-slate-300 rounded transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
            </div>
          </div>

          {/* List */}
          <div className="max-h-48 overflow-y-auto">
            {hiddenList.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between px-4 py-2.5 hover:bg-slate-800/50 transition-colors border-b border-slate-800/50 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-300 truncate font-medium">{item.tableName}</p>
                  <p className="text-[10px] text-slate-600">{item.schemaName} &middot; {item.columnCount} columns</p>
                </div>
                <button
                  onClick={() => onRestore(item.id)}
                  className="ml-3 px-2.5 py-1 text-[11px] text-indigo-400 border border-indigo-500/30 rounded-lg hover:bg-indigo-500/10 hover:text-indigo-300 transition-colors flex-shrink-0"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-2 px-4 py-2.5 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-slate-300 hover:bg-slate-800 hover:text-slate-100 hover:border-slate-600 transition-all shadow-xl backdrop-blur-sm"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </svg>
          Hidden Tables ({hiddenTables.size})
        </button>
      )}
    </div>
  )
}
