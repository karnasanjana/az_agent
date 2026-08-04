'use client'

import { useState } from 'react'
import type { DatabaseInfo } from '@/types/schema'

const PALETTE = [
  'bg-blue-900/40 border-blue-500/50 text-blue-200 ring-1 ring-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]',
  'bg-emerald-900/40 border-emerald-500/50 text-emerald-200 ring-1 ring-emerald-500/30 shadow-[0_0_15px_rgba(16,185,129,0.15)]',
  'bg-indigo-900/40 border-indigo-500/50 text-indigo-200 ring-1 ring-indigo-500/30 shadow-[0_0_15px_rgba(68,147,248,0.15)]',
  'bg-orange-900/40 border-orange-500/50 text-orange-200 ring-1 ring-orange-500/30 shadow-[0_0_15px_rgba(249,115,22,0.15)]',
  'bg-pink-900/40 border-pink-500/50 text-pink-200 ring-1 ring-pink-500/30 shadow-[0_0_15px_rgba(236,72,153,0.15)]',
  'bg-teal-900/40 border-teal-500/50 text-teal-200 ring-1 ring-teal-500/30 shadow-[0_0_15px_rgba(20,184,166,0.15)]',
  'bg-indigo-900/40 border-indigo-500/50 text-indigo-200 ring-1 ring-indigo-500/30 shadow-[0_0_15px_rgba(99,102,241,0.15)]',
  'bg-amber-900/40 border-amber-500/50 text-amber-200 ring-1 ring-amber-500/30 shadow-[0_0_15px_rgba(245,158,11,0.15)]',
]

interface DatabasePickerProps {
  databases: DatabaseInfo[]
  onSelect: (selected: string[]) => void
  selectedDatabases: string[]
  label?: string // "databases" or "datasets"
}

export default function DatabasePicker({
  databases,
  onSelect,
  selectedDatabases,
  label = 'databases',
}: DatabasePickerProps) {
  const [search, setSearch] = useState('')

  const filteredDatabases = search.trim()
    ? databases.filter((db) => db.name.toLowerCase().includes(search.toLowerCase()))
    : databases

  const totalSelected = selectedDatabases.length
  const totalTables = databases
    .filter((db) => selectedDatabases.includes(db.name))
    .reduce((sum, db) => sum + (db.table_count || 0), 0)

  const toggleDatabase = (name: string) => {
    if (selectedDatabases.includes(name)) {
      onSelect(selectedDatabases.filter((d) => d !== name))
    } else {
      onSelect([...selectedDatabases, name])
    }
  }

  const selectAll = () => {
    onSelect(databases.map((db) => db.name))
  }

  const clearAll = () => {
    onSelect([])
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-slate-200">
          Select {label} to extract
        </h3>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={selectAll}
            className="text-xs text-indigo-400 hover:text-indigo-300 font-medium transition-colors"
          >
            Select All
          </button>
          <span className="text-slate-600">|</span>
          <button
            type="button"
            onClick={clearAll}
            className="text-xs text-slate-400 hover:text-slate-300 font-medium transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Search bar */}
      {databases.length > 6 && (
        <div className="mb-3">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${label}...`}
            className="w-full px-3 py-2 text-sm border border-slate-700 bg-slate-900/50 text-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all placeholder-slate-500"
          />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 max-h-80 overflow-y-auto pr-1">
        {filteredDatabases.map((db, index) => {
          const isSelected = selectedDatabases.includes(db.name)
          const colorClasses = PALETTE[index % PALETTE.length]

          return (
            <button
              key={db.name}
              type="button"
              onClick={() => toggleDatabase(db.name)}
              className={`relative p-3 rounded-xl border text-left transition-all ${
                isSelected
                  ? `${colorClasses} backdrop-blur-sm -translate-y-1`
                  : 'bg-slate-800/50 border-slate-700 hover:border-slate-600 hover:bg-slate-800 text-slate-300'
              }`}
            >
              {isSelected && (
                <div className="absolute top-2 right-2 drop-shadow-[0_0_5px_rgba(255,255,255,0.5)]">
                  <svg
                    className="w-4 h-4 text-white"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
              )}
              <p className="font-medium text-sm truncate pr-5">{db.name}</p>
              <p className={`text-xs mt-1 transition-colors ${isSelected ? 'text-white/80 font-medium' : 'text-slate-500'}`}>
                {label === 'entities' ? 'table' : `${db.table_count ?? 0} table${(db.table_count ?? 0) !== 1 ? 's' : ''}`}
              </p>
            </button>
          )
        })}
      </div>

      {/* Summary footer */}
      <div className="mt-5 pt-4 border-t border-slate-700/50">
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400 font-medium tracking-wide">
            {totalSelected} {label} selected &middot; {totalTables} total tables
          </span>
        </div>
        {totalTables > 100 && (
          <div className="mt-3 p-3 bg-amber-900/40 border border-amber-500/30 rounded-lg backdrop-blur-sm animate-fadeIn">
            <p className="text-xs text-amber-200 flex items-center gap-1.5">
              <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              Large selection: {totalTables} tables may take longer to extract.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
