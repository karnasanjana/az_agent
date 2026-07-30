'use client'

import { useMemo } from 'react'
import type { DatabaseSchema, ForeignKey } from '@/types/schema'
import type { ManualRelationship } from '@/types/diagram'

interface LineagePanelProps {
  isOpen: boolean
  onClose: () => void
  schema: DatabaseSchema | null
  manualRelationships: ManualRelationship[]
}

type SourceType = 'bigquery' | 'sqlserver' | 'dataverse'

const SOURCE_COLORS: Record<SourceType, { bg: string; border: string; text: string; node: string }> = {
  sqlserver: { bg: 'bg-emerald-900/30', border: 'border-emerald-500/40', text: 'text-emerald-400', node: '#10b981' },
  bigquery: { bg: 'bg-blue-900/30', border: 'border-blue-500/40', text: 'text-blue-400', node: '#3b82f6' },
  dataverse: { bg: 'bg-purple-900/30', border: 'border-purple-500/40', text: 'text-purple-400', node: '#a855f7' },
}

const SOURCE_LABELS: Record<SourceType, string> = {
  bigquery: 'BigQuery',
  sqlserver: 'SQL Server',
  dataverse: 'Dataverse',
}

interface DatabaseNode {
  name: string
  source: SourceType | 'unknown'
  tables: string[]
  tableCount: number
}

interface LineageEdge {
  from: string
  to: string
  relationships: string[]
  count: number
}

export function LineagePanel({ isOpen, onClose, schema, manualRelationships }: LineagePanelProps) {
  const { databases, edges, crossDbRelCount } = useMemo(() => {
    if (!schema) return { databases: [], edges: [], crossDbRelCount: 0 }

    const sources = schema.dataset_sources || {}
    const datasets = Array.from(new Set(schema.tables.map((t) => t.schema_name)))

    // Build database nodes
    const dbNodes: DatabaseNode[] = datasets.map((ds) => ({
      name: ds,
      source: (sources[ds] as SourceType) || 'unknown',
      tables: schema.tables.filter((t) => t.schema_name === ds).map((t) => t.table_name),
      tableCount: schema.tables.filter((t) => t.schema_name === ds).length,
    }))

    // Find cross-database FK edges
    const edgeMap = new Map<string, LineageEdge>()

    for (const fk of schema.foreign_keys) {
      if (fk.source_schema !== fk.target_schema) {
        const key = `${fk.source_schema}→${fk.target_schema}`
        const existing = edgeMap.get(key)
        const label = `${fk.source_table}.${fk.source_columns[0]} → ${fk.target_table}.${fk.target_columns[0]}`
        if (existing) {
          existing.relationships.push(label)
          existing.count++
        } else {
          edgeMap.set(key, {
            from: fk.source_schema,
            to: fk.target_schema,
            relationships: [label],
            count: 1,
          })
        }
      }
    }

    // Add manual cross-database relationships
    for (const rel of manualRelationships) {
      if (rel.source_database !== rel.target_database) {
        const key = `${rel.source_database}→${rel.target_database}`
        const existing = edgeMap.get(key)
        const label = `${rel.source_table}.${rel.source_column} → ${rel.target_table}.${rel.target_column}`
        if (existing) {
          existing.relationships.push(label)
          existing.count++
        } else {
          edgeMap.set(key, {
            from: rel.source_database,
            to: rel.target_database,
            relationships: [label],
            count: 1,
          })
        }
      }
    }

    const edgeList = Array.from(edgeMap.values())
    const crossCount = edgeList.reduce((sum, e) => sum + e.count, 0)

    return { databases: dbNodes, edges: edgeList, crossDbRelCount: crossCount }
  }, [schema, manualRelationships])

  if (!isOpen) return null

  const hasCrossDb = databases.length > 1

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-[520px] z-50 glass-panel bg-slate-900/95 border-l border-slate-700 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-200">Data Lineage</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {databases.length} database{databases.length !== 1 ? 's' : ''} connected
              {crossDbRelCount > 0 && ` \u00b7 ${crossDbRelCount} cross-database link${crossDbRelCount !== 1 ? 's' : ''}`}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Visual lineage map */}
          <div className="px-5 py-6">
            {databases.length === 0 && (
              <p className="text-sm text-slate-500 text-center py-8">No databases loaded.</p>
            )}

            {databases.length === 1 && (
              <div className="text-center py-6">
                <DatabaseCard db={databases[0]} />
                <p className="text-xs text-slate-500 mt-4">
                  Add more data sources to see cross-database lineage.
                </p>
              </div>
            )}

            {hasCrossDb && (
              <div className="space-y-0">
                {/* Render databases as flow */}
                <div className="flex flex-col items-center gap-0">
                  {databases.map((db, i) => (
                    <div key={db.name} className="flex flex-col items-center w-full">
                      <DatabaseCard db={db} />

                      {/* Edges going out from this database */}
                      {i < databases.length - 1 && (
                        <div className="py-2 w-full">
                          {edges
                            .filter((e) => e.from === db.name || e.to === db.name)
                            .filter((e, idx, arr) =>
                              // Deduplicate: only show once per pair
                              arr.findIndex((a) =>
                                (a.from === e.from && a.to === e.to) || (a.from === e.to && a.to === e.from)
                              ) === idx
                            )
                            .filter((e) => {
                              // Only render between current db and the next db in sequence
                              const otherDb = e.from === db.name ? e.to : e.from
                              const otherIdx = databases.findIndex((d) => d.name === otherDb)
                              return otherIdx > i
                            })
                            .map((edge) => (
                              <EdgeConnector key={`${edge.from}→${edge.to}`} edge={edge} />
                            ))}
                          {/* Default connector line if no edges */}
                          {!edges.some((e) =>
                            (e.from === db.name || e.to === db.name) &&
                            databases.findIndex((d) => d.name === (e.from === db.name ? e.to : e.from)) > i
                          ) && (
                            <div className="flex justify-center py-1">
                              <div className="w-px h-6 bg-slate-700/50" />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Detailed cross-database relationships */}
          {edges.length > 0 && (
            <div className="px-5 py-4 border-t border-slate-800">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Cross-Database Relationships</h3>
              <div className="space-y-3">
                {edges.map((edge) => (
                  <div key={`${edge.from}→${edge.to}`} className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-3.5">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-medium text-slate-300">{edge.from}</span>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400 flex-shrink-0">
                        <path d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                      <span className="text-xs font-medium text-slate-300">{edge.to}</span>
                      <span className="ml-auto text-[10px] px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 rounded-full">
                        {edge.count} link{edge.count !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className="space-y-0.5">
                      {edge.relationships.map((rel, i) => (
                        <p key={i} className="text-[11px] font-mono text-slate-500">{rel}</p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-database table summary */}
          <div className="px-5 py-4 border-t border-slate-800">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Database Summary</h3>
            <div className="space-y-2">
              {databases.map((db) => {
                const src = db.source as SourceType
                const colors = SOURCE_COLORS[src] || { bg: 'bg-slate-800/40', border: 'border-slate-700/40', text: 'text-slate-400' }
                const intraFks = schema!.foreign_keys.filter(
                  (fk) => fk.source_schema === db.name && fk.target_schema === db.name
                ).length
                const crossFks = edges.filter((e) => e.from === db.name || e.to === db.name)
                  .reduce((sum, e) => sum + e.count, 0)

                return (
                  <div key={db.name} className={`rounded-lg p-3 border ${colors.bg} ${colors.border}`}>
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-medium ${colors.text}`}>
                        {db.name}
                      </span>
                      <span className="text-xs text-slate-500">
                        {SOURCE_LABELS[src] || 'Unknown'}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-[11px] text-slate-500">
                      <span>{db.tableCount} tables</span>
                      <span>{intraFks} internal FKs</span>
                      {crossFks > 0 && <span className="text-indigo-400">{crossFks} cross-DB links</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function DatabaseCard({ db }: { db: DatabaseNode }) {
  const src = db.source as SourceType
  const colors = SOURCE_COLORS[src] || { bg: 'bg-slate-800/60', border: 'border-slate-600', text: 'text-slate-300', node: '#94a3b8' }
  const icon = src === 'bigquery' ? 'BQ' : src === 'sqlserver' ? 'SQL' : src === 'dataverse' ? 'DV' : 'DB'

  return (
    <div className={`w-full rounded-xl p-4 border-2 ${colors.bg} ${colors.border} transition-all`}>
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center text-xs font-bold text-white"
          style={{ backgroundColor: colors.node }}
        >
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${colors.text} truncate`}>{db.name}</p>
          <p className="text-[11px] text-slate-500">
            {SOURCE_LABELS[src] || 'Database'} \u00b7 {db.tableCount} table{db.tableCount !== 1 ? 's' : ''}
          </p>
        </div>
      </div>
    </div>
  )
}

function EdgeConnector({ edge }: { edge: LineageEdge }) {
  return (
    <div className="flex items-center justify-center gap-2 py-1">
      <div className="flex flex-col items-center">
        <div className="w-px h-3 bg-indigo-500/40" />
        <div className="flex items-center gap-1.5 px-3 py-1 bg-indigo-900/30 border border-indigo-500/30 rounded-full">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-indigo-400">
            <path d="M12 5v14M5 12l7 7 7-7" />
          </svg>
          <span className="text-[10px] font-medium text-indigo-400">
            {edge.count} link{edge.count !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="w-px h-3 bg-indigo-500/40" />
      </div>
    </div>
  )
}
