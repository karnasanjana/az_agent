'use client'

import { useState, useEffect, useMemo } from 'react'
import UserMenu from '@/components/user-menu'
import { ZionLogo } from '@/components/zion-logo'
import type { DatabaseSchema, Table, Column } from '@/types/schema'

type SourceType = 'bigquery' | 'sqlserver' | 'dataverse'

const SOURCE_LABELS: Record<SourceType, string> = {
  bigquery: 'BigQuery',
  sqlserver: 'SQL Server',
  dataverse: 'Dataverse',
}

const SOURCE_COLORS: Record<SourceType, string> = {
  bigquery: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  sqlserver: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  dataverse: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30',
}

export default function DataDictionaryPage() {
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [search, setSearch] = useState('')
  const [filterDataset, setFilterDataset] = useState('')
  const [filterType, setFilterType] = useState<'' | 'table' | 'view'>('')
  const [expandedTable, setExpandedTable] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'name' | 'columns' | 'dataset'>('dataset')

  useEffect(() => {
    // Show a schema only when a diagram is actually open/saved (current_diagram_id).
    // extracted_schema persists across reloads, so without this gate a stale
    // extraction from a previous session would show even though nothing is
    // connected. We don't delete extracted_schema here — the diagram page may
    // still hold unsaved work; we just don't display stale data in the dictionary.
    const hasDiagram = sessionStorage.getItem('current_diagram_id')
    const stored = sessionStorage.getItem('extracted_schema')
    if (hasDiagram && stored) {
      try {
        setSchema(JSON.parse(stored))
      } catch {
        // ignore
      }
    }
  }, [])

  const datasets = useMemo(() => {
    if (!schema) return []
    return Array.from(new Set(schema.tables.map((t) => t.schema_name))).sort()
  }, [schema])

  const datasetSources = schema?.dataset_sources || {}

  const filteredTables = useMemo(() => {
    if (!schema) return []
    let tables = [...schema.tables]

    // Search filter
    if (search.trim()) {
      const q = search.toLowerCase()
      tables = tables.filter((t) =>
        t.table_name.toLowerCase().includes(q) ||
        t.schema_name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        t.columns.some((c) =>
          c.name.toLowerCase().includes(q) ||
          (c.description || '').toLowerCase().includes(q)
        )
      )
    }

    // Dataset filter
    if (filterDataset) {
      tables = tables.filter((t) => t.schema_name === filterDataset)
    }

    // Type filter
    if (filterType === 'view') {
      tables = tables.filter((t) => t.is_view)
    } else if (filterType === 'table') {
      tables = tables.filter((t) => !t.is_view)
    }

    // Sort
    if (sortBy === 'name') {
      tables.sort((a, b) => a.table_name.localeCompare(b.table_name))
    } else if (sortBy === 'columns') {
      tables.sort((a, b) => b.columns.length - a.columns.length)
    } else {
      tables.sort((a, b) => {
        const cmp = a.schema_name.localeCompare(b.schema_name)
        return cmp !== 0 ? cmp : a.table_name.localeCompare(b.table_name)
      })
    }

    return tables
  }, [schema, search, filterDataset, filterType, sortBy])

  // Stats
  const totalColumns = useMemo(() =>
    filteredTables.reduce((sum, t) => sum + t.columns.length, 0),
    [filteredTables]
  )
  const totalFks = schema?.foreign_keys.length || 0

  const handleExportCsv = () => {
    if (!schema) return
    const rows = [['Database', 'Table', 'Type', 'Column', 'Data Type', 'Nullable', 'Primary Key', 'Table Description', 'Column Description']]
    for (const table of filteredTables) {
      for (const col of table.columns) {
        rows.push([
          table.schema_name,
          table.table_name,
          table.is_view ? 'View' : 'Table',
          col.name,
          col.data_type,
          col.is_nullable ? 'Yes' : 'No',
          col.is_primary_key ? 'Yes' : 'No',
          (table.description || '').replace(/"/g, '""'),
          (col.description || '').replace(/"/g, '""'),
        ])
      }
    }
    const csv = rows.map((r) => r.map((v) => `"${v}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `data_dictionary_${schema.database_name || 'schema'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!schema) {
    return (
      <main className="min-h-screen bg-gradient-surface flex items-center justify-center">
        <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-10 text-center max-w-md">
          <h1 className="text-xl font-bold text-slate-200 mb-2">No Schema Loaded</h1>
          <p className="text-slate-400 text-sm mb-6">Open a diagram first to view its data dictionary.</p>
          <a href="/diagrams" className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 transition-colors font-medium text-sm">
            My Diagrams
          </a>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gradient-surface flex flex-col">
      {/* Header */}
      <header className="glass-panel border-b border-white/10 text-white flex-shrink-0 relative z-30">
        <div className="px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/diagram" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <ZionLogo className="h-8 text-white drop-shadow-[0_0_15px_rgba(79,70,229,0.4)]" />
              <div className="h-6 w-px bg-slate-700/80 mx-2" />
              <span className="text-xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-100 to-slate-300">
                Data Dictionary
              </span>
            </a>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleExportCsv}
              className="px-4 py-2 text-sm bg-slate-800 border border-slate-700 text-slate-300 rounded-xl hover:bg-slate-700 hover:text-white transition-colors font-medium"
            >
              Export CSV
            </button>
            <a
              href="/diagram"
              className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 border border-indigo-500/50 shadow-[0_0_15px_rgba(79,70,229,0.4)] transition-all font-medium"
            >
              Back to Diagram
            </a>
            <UserMenu />
          </div>
        </div>
      </header>

      {/* Stats bar */}
      <div className="px-8 py-4 border-b border-slate-700/50 flex items-center gap-6 flex-shrink-0">
        <div className="flex items-center gap-6">
          <Stat label="Databases" value={datasets.length} />
          <Stat label="Tables" value={filteredTables.length} total={schema.tables.length} />
          <Stat label="Columns" value={totalColumns} />
          <Stat label="Relationships" value={totalFks} />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {datasets.map((ds) => {
            const src = datasetSources[ds] as SourceType | undefined
            return (
              <span
                key={ds}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${
                  src ? SOURCE_COLORS[src] : 'bg-slate-500/20 text-slate-400 border-slate-500/30'
                }`}
              >
                {src ? SOURCE_LABELS[src] : 'Unknown'}
                <span className="text-[10px] opacity-70">{ds}</span>
              </span>
            )
          })}
        </div>
      </div>

      {/* Filters */}
      <div className="px-8 py-3 border-b border-slate-700/50 flex items-center gap-3 flex-shrink-0">
        <div className="relative flex-1 max-w-md">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tables, columns, or descriptions..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-slate-900/60 border border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-slate-200 placeholder:text-slate-500"
          />
        </div>
        <select
          value={filterDataset}
          onChange={(e) => setFilterDataset(e.target.value)}
          className="px-3 py-2 text-sm bg-slate-900/60 border border-slate-700 rounded-lg text-slate-300 focus:outline-none"
        >
          <option value="">All databases</option>
          {datasets.map((ds) => (
            <option key={ds} value={ds}>{ds}</option>
          ))}
        </select>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as '' | 'table' | 'view')}
          className="px-3 py-2 text-sm bg-slate-900/60 border border-slate-700 rounded-lg text-slate-300 focus:outline-none"
        >
          <option value="">Tables & Views</option>
          <option value="table">Tables only</option>
          <option value="view">Views only</option>
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as 'name' | 'columns' | 'dataset')}
          className="px-3 py-2 text-sm bg-slate-900/60 border border-slate-700 rounded-lg text-slate-300 focus:outline-none"
        >
          <option value="dataset">Sort by database</option>
          <option value="name">Sort by name</option>
          <option value="columns">Sort by column count</option>
        </select>
      </div>

      {/* Table list */}
      <div className="flex-1 overflow-y-auto px-8 py-4">
        {filteredTables.length === 0 && (
          <div className="text-center py-16">
            <p className="text-slate-500 text-sm">No tables match your filters.</p>
          </div>
        )}

        <div className="space-y-2">
          {filteredTables.map((table) => {
            const key = `${table.schema_name}.${table.table_name}`
            const isExpanded = expandedTable === key
            const src = datasetSources[table.schema_name] as SourceType | undefined
            const pkColumns = table.columns.filter((c) => c.is_primary_key)
            // Find FKs referencing this table
            const incomingFks = schema.foreign_keys.filter((fk) => fk.target_table === table.table_name)
            const outgoingFks = schema.foreign_keys.filter((fk) => fk.source_table === table.table_name)

            return (
              <div key={key} className="glass-panel bg-slate-900/50 border border-slate-700/60 rounded-xl overflow-hidden">
                {/* Table header row */}
                <button
                  onClick={() => setExpandedTable(isExpanded ? null : key)}
                  className="w-full px-5 py-3.5 flex items-center gap-3 hover:bg-slate-800/40 transition-colors text-left"
                >
                  <svg
                    className={`w-4 h-4 text-slate-500 flex-shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-200">{table.table_name}</span>
                      <span className="text-[10px] text-slate-500">{table.schema_name}</span>
                      {table.is_view && (
                        <span className="px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/20 text-amber-400 border border-amber-500/20 rounded">VIEW</span>
                      )}
                      {src && (
                        <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${SOURCE_COLORS[src]}`}>
                          {SOURCE_LABELS[src]}
                        </span>
                      )}
                    </div>
                    {table.description && (
                      <p className="text-xs text-slate-500 mt-0.5 truncate">{table.description}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-4 text-xs text-slate-500 flex-shrink-0">
                    <span>{table.columns.length} cols</span>
                    {pkColumns.length > 0 && <span>{pkColumns.length} PK</span>}
                    {outgoingFks.length > 0 && <span>{outgoingFks.length} FK out</span>}
                    {incomingFks.length > 0 && <span>{incomingFks.length} FK in</span>}
                  </div>
                </button>

                {/* Expanded: columns table */}
                {isExpanded && (
                  <div className="border-t border-slate-700/50 bg-slate-950/30">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-700/30">
                          <th className="px-5 py-2 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Column</th>
                          <th className="px-3 py-2 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Type</th>
                          <th className="px-3 py-2 text-center text-[10px] font-semibold text-slate-500 uppercase tracking-wider">PK</th>
                          <th className="px-3 py-2 text-center text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Nullable</th>
                          <th className="px-3 py-2 text-left text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Description</th>
                        </tr>
                      </thead>
                      <tbody>
                        {table.columns.map((col) => {
                          const isFk = outgoingFks.some((fk) => fk.source_columns.includes(col.name))
                          return (
                            <tr key={col.name} className="border-b border-slate-800/30 hover:bg-slate-800/20">
                              <td className="px-5 py-1.5 font-mono text-xs text-slate-300">
                                <span className="flex items-center gap-1.5">
                                  {col.name}
                                  {col.is_primary_key && (
                                    <span className="text-amber-400" title="Primary Key">
                                      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12.65 10C11.83 7.67 9.61 6 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6c2.61 0 4.83-1.67 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z"/></svg>
                                    </span>
                                  )}
                                  {isFk && (
                                    <span className="text-indigo-400" title="Foreign Key">
                                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/></svg>
                                    </span>
                                  )}
                                </span>
                              </td>
                              <td className="px-3 py-1.5 font-mono text-xs text-slate-500">{col.data_type}</td>
                              <td className="px-3 py-1.5 text-center">
                                {col.is_primary_key && <span className="text-amber-400 text-xs">PK</span>}
                              </td>
                              <td className="px-3 py-1.5 text-center text-xs text-slate-500">
                                {col.is_nullable ? 'Yes' : 'No'}
                              </td>
                              <td className="px-3 py-1.5 text-xs text-slate-500 max-w-xs truncate">
                                {col.description || '-'}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>

                    {/* FK relationships for this table */}
                    {(outgoingFks.length > 0 || incomingFks.length > 0) && (
                      <div className="px-5 py-3 border-t border-slate-700/30 space-y-1">
                        {outgoingFks.map((fk) => (
                          <p key={fk.constraint_name} className="text-[11px] text-indigo-400 font-mono">
                            {fk.source_columns.join(', ')} → {fk.target_schema}.{fk.target_table}.{fk.target_columns.join(', ')}
                          </p>
                        ))}
                        {incomingFks.map((fk) => (
                          <p key={fk.constraint_name} className="text-[11px] text-emerald-400 font-mono">
                            ← {fk.source_schema}.{fk.source_table}.{fk.source_columns.join(', ')}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </main>
  )
}

function Stat({ label, value, total }: { label: string; value: number; total?: number }) {
  return (
    <div>
      <p className="text-xs text-slate-500 uppercase tracking-wider">{label}</p>
      <p className="text-lg font-bold text-slate-200">
        {value}
        {total !== undefined && total !== value && (
          <span className="text-sm font-normal text-slate-500">/{total}</span>
        )}
      </p>
    </div>
  )
}
