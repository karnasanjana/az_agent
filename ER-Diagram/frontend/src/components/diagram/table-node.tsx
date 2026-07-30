'use client'

import { useState, useCallback } from 'react'
import { Handle, Position, NodeResizer, type NodeProps } from '@xyflow/react'
import type { TableNode as TableNodeType } from '@/types/diagram'
import type { DataSource } from '@/types/chat'
import { getApiBaseUrl } from '@/app/actions'

interface SampleDataState {
  loading: boolean
  error: string | null
  columns: string[]
  rows: unknown[][]
}

function getSampleDataSources(): DataSource[] {
  if (typeof window === 'undefined') return []
  const sources: DataSource[] = []
  const projectId = sessionStorage.getItem('bq_project_id') || ''
  const accessToken = sessionStorage.getItem('bq_access_token') || ''
  if (projectId && accessToken) {
    sources.push({ type: 'bigquery', project_id: projectId, access_token: accessToken })
  }
  try {
    const creds = JSON.parse(sessionStorage.getItem('db_credentials') || '{}')
    if (creds.host) {
      sources.push({
        type: 'sqlserver',
        host: creds.host,
        port: creds.port || 1433,
        database: creds.database,
        username: creds.username,
        password: creds.password,
      })
    }
  } catch { /* ignore */ }
  return sources
}

/**
 * Key icon SVG for primary key columns
 */
function KeyIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  )
}

/**
 * Link icon SVG for foreign key columns
 */
function LinkIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  )
}

/**
 * Custom React Flow node for displaying database tables.
 * Features:
 * - Blue header bar with table name in "TableName (schema)" format
 * - White body with column list
 * - PK columns: key icon + bold text
 * - FK columns: link icon (determined by parent passing isForeignKey)
 * - Nullable columns: "?" marker
 * - Data types: shown on hover via title attribute
 * - Resizable via NodeResizer
 * - Handles on left/right for edge connections
 */
export function TableNode({ data, selected }: NodeProps<TableNodeType>) {
  const isView = !!(data as any).is_view
  const displayName = `${data.table_name} (${data.schema_name})`
  const hasCustomColor = !!data.datasetColor
  const headerColor = hasCustomColor ? '' : (isView ? 'bg-purple-600/90' : 'bg-indigo-600/90')
  const accentColor = isView ? 'border-purple-400' : 'border-indigo-400'
  const handleColor = hasCustomColor ? '' : (isView ? 'bg-purple-500' : 'bg-indigo-500')
  const headerStyle = hasCustomColor ? { backgroundColor: data.datasetColor } : undefined
  const handleStyle = hasCustomColor ? { backgroundColor: data.datasetColor } : undefined

  // Sample-data preview state — cached per node instance
  const [sample, setSample] = useState<SampleDataState | null>(null)
  const [showSample, setShowSample] = useState(false)

  const fetchSample = useCallback(async () => {
    if (sample && !sample.error) {
      setShowSample((v) => !v)
      return
    }
    setShowSample(true)
    setSample({ loading: true, error: null, columns: [], rows: [] })
    try {
      const apiBase = await getApiBaseUrl()
      const dataSources = getSampleDataSources()
      const response = await fetch(`${apiBase}/api/schema/sample`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          table_name: data.table_name,
          schema_name: data.schema_name,
          limit: 5,
          data_sources: dataSources,
        }),
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${response.status}`)
      }
      const json = await response.json()
      setSample({
        loading: false,
        error: null,
        columns: json.columns || [],
        rows: json.rows || [],
      })
    } catch (err) {
      setSample({
        loading: false,
        error: err instanceof Error ? err.message : 'Failed to fetch sample',
        columns: [],
        rows: [],
      })
    }
  }, [data.table_name, data.schema_name, sample])

  const handleSampleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      fetchSample()
    },
    [fetchSample]
  )

  return (
    <>
      {/* Resizer handles - only visible when selected */}
      <NodeResizer
        minWidth={200}
        minHeight={100}
        isVisible={selected}
        lineClassName={accentColor}
        handleClassName={`h-3 w-3 bg-slate-900 border-2 ${accentColor} rounded`}
      />

      {/* Connection handles for edges */}
      <Handle
        type="target"
        position={Position.Left}
        className={`w-3 h-3 ${handleColor} border-2 border-slate-800`}
        style={handleStyle}
      />
      <Handle
        type="source"
        position={Position.Right}
        className={`w-3 h-3 ${handleColor} border-2 border-slate-800`}
        style={handleStyle}
      />

      {/* Node content */}
      <div className={`rounded-xl shadow-[0_5px_20px_rgba(0,0,0,0.6)] overflow-hidden min-w-[200px] max-h-[560px] flex flex-col bg-slate-900/90 backdrop-blur-xl border ${selected ? accentColor : 'border-slate-700/80'}`}>
        {/* Header - Blue for tables, Purple for views */}
        <div className={`${headerColor} px-3 py-2 flex items-center gap-2 flex-shrink-0`} style={headerStyle}>
          {isView && (
            <span className="text-white/80 text-[10px] font-medium uppercase tracking-wider bg-white/20 px-1.5 py-0.5 rounded">
              View
            </span>
          )}
          <div className="flex flex-col min-w-0 flex-1">
            <h3 className="text-white font-bold text-sm truncate" title={displayName}>
              {displayName}
            </h3>
            {data.description && (
              <p
                className="text-white/70 text-[10px] italic truncate leading-tight mt-0.5"
                title={data.description}
              >
                {data.description}
              </p>
            )}
          </div>
          <button
            onClick={handleSampleClick}
            onPointerDown={(e) => e.stopPropagation()}
            className="text-white/80 hover:text-white p-0.5 rounded hover:bg-white/10 transition-colors flex-shrink-0 nodrag"
            title={showSample ? 'Hide sample data' : 'Show sample data'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {showSample ? (
                <polyline points="18 15 12 9 6 15" />
              ) : (
                <polyline points="6 9 12 15 18 9" />
              )}
            </svg>
          </button>
          {typeof data.onHideTable === 'function' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                (data.onHideTable as (tableId: string) => void)(`${data.schema_name}.${data.table_name}`)
              }}
              onPointerDown={(e) => e.stopPropagation()}
              className="text-white/50 hover:text-red-300 p-0.5 rounded hover:bg-red-500/20 transition-colors flex-shrink-0 nodrag"
              title="Hide table from diagram"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>

        {/* Body - Column list (scrollable, nowheel prevents React Flow from capturing scroll) */}
        <div className="px-2 py-2 overflow-y-auto flex-1 nowheel">
          {data.columns.length === 0 ? (
            <p className="text-slate-500 text-xs italic">No columns</p>
          ) : (
            <ul className="space-y-1">
              {data.columns.map((column) => (
                <li
                  key={column.name}
                  className="flex items-center gap-1.5 text-xs group"
                  title={`${column.name}: ${column.data_type}${column.is_nullable ? ' (nullable)' : ' (not null)'}${column.description ? `\n${column.description}` : ''}`}
                >
                  {/* Icons container */}
                  <span className="flex items-center gap-0.5 w-8 flex-shrink-0">
                    {column.is_primary_key && (
                      <KeyIcon className="text-amber-500" />
                    )}
                    {data.fkColumns?.has(column.name) && (
                      <LinkIcon className="text-indigo-400" />
                    )}
                  </span>

                  {/* Column name */}
                  <span
                    className={`truncate flex-1 ${
                      column.is_primary_key ? 'font-bold text-slate-200' : 'text-slate-400'
                    }`}
                  >
                    {column.name}
                  </span>

                  {/* Nullable indicator */}
                  {column.is_nullable && (
                    <span className="text-slate-600 text-[10px] flex-shrink-0" title="Nullable">
                      ?
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Sample data preview */}
        {showSample && (
          <div className="border-t border-slate-700/80 px-2 py-2 bg-slate-950/60 nowheel max-h-[160px] overflow-auto flex-shrink-0">
            {sample?.loading && (
              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                <svg className="animate-spin h-3 w-3 text-indigo-400" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                  <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" className="opacity-75" />
                </svg>
                Loading sample…
              </div>
            )}
            {sample?.error && (
              <p className="text-[10px] text-red-400 break-words" title={sample.error}>
                {sample.error}
              </p>
            )}
            {sample && !sample.loading && !sample.error && sample.rows.length === 0 && (
              <p className="text-[10px] text-slate-500 italic">No rows</p>
            )}
            {sample && !sample.loading && !sample.error && sample.rows.length > 0 && (
              <table className="text-[10px] w-full text-slate-300">
                <thead>
                  <tr className="text-indigo-300">
                    {sample.columns.map((c) => (
                      <th key={c} className="text-left pr-2 pb-1 font-medium whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sample.rows.map((row, ri) => (
                    <tr key={ri} className="border-t border-slate-800">
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className="pr-2 py-0.5 truncate max-w-[120px]"
                          title={cell == null ? 'NULL' : String(cell)}
                        >
                          {cell == null ? <span className="text-slate-600 italic">NULL</span> : String(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  )
}

/**
 * Node type registration for React Flow.
 * Use this in the ReactFlow nodeTypes prop.
 */
export const tableNodeTypes = {
  tableNode: TableNode,
}
