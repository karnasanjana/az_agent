'use client'

import { useState } from 'react'
import type { QueryStep, QuerySourceResult } from '@/types/chat'

const PREVIEW_ROWS = 50

interface QueryResultProps {
  queryPlan: QueryStep[]
  sources: QuerySourceResult[]
}

export default function QueryResult({ queryPlan, sources, merged }: QueryResultProps & { merged?: QuerySourceResult }) {
  return (
    <div className="mt-2 space-y-3">
      {/* Show merged result first if available */}
      {merged && !merged.error && (
        <MergedResult source={merged} />
      )}

      {/* Show individual source results */}
      {sources.map((source, idx) => (
        <SourceResult
          key={source.alias}
          source={source}
          step={queryPlan[idx]}
          collapsed={!!merged && !merged.error}
        />
      ))}
    </div>
  )
}

function MergedResult({ source }: { source: QuerySourceResult }) {
  return (
    <div className="border-2 border-green-300 rounded-lg overflow-hidden bg-white">
      <div className="px-2.5 py-1.5 bg-green-50 border-b border-green-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="text-xs">✅</span>
            <span className="text-xs font-medium text-green-800">Merged Result</span>
            <span className="text-[10px] text-green-600">(cross-database join)</span>
          </div>
          {source.row_count !== undefined && (
            <span className="text-[10px] text-green-600">
              {source.row_count} row{source.row_count !== 1 ? 's' : ''}
              {source.truncated && ' (truncated)'}
            </span>
          )}
        </div>
      </div>
      {source.columns && source.rows && source.rows.length > 0 ? (
        <div className="overflow-x-auto max-h-72">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-green-50">
                {source.columns.map((col) => (
                  <th key={col} className="px-2 py-1 text-left font-medium text-green-800 border-b border-green-200 whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {source.rows.map((row, rowIdx) => (
                <tr key={rowIdx} className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-green-50/30'}>
                  {row.map((cell, cellIdx) => (
                    <td key={cellIdx} className="px-2 py-1 text-gray-700 border-b border-gray-100 whitespace-nowrap max-w-[200px] truncate"
                      title={cell != null ? String(cell) : 'NULL'}>
                      {cell != null ? String(cell) : <span className="text-gray-400 italic">NULL</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="px-2.5 py-3 text-xs text-gray-500 text-center">No results after merge</div>
      )}
    </div>
  )
}

function SourceResult({ source, step, collapsed = false }: { source: QuerySourceResult; step?: QueryStep; collapsed?: boolean }) {
  const [showQuery, setShowQuery] = useState(false)
  const [expanded, setExpanded] = useState(!collapsed)

  const sourceLabel = step?.source === 'bigquery' ? 'BigQuery' : 'SQL Server'
  const sourceIcon = step?.source === 'bigquery' ? '☁️' : '🗄️'

  if (source.error) {
    return (
      <div className="border border-red-200 rounded-lg p-2 bg-red-50">
        <div className="text-xs font-medium text-red-700 mb-1">
          {sourceIcon} {source.alias} ({sourceLabel}) — Error
        </div>
        <p className="text-xs text-red-600">{source.error}</p>
        {step && (
          <button
            onClick={() => setShowQuery(!showQuery)}
            className="text-[10px] text-red-500 underline mt-1"
          >
            {showQuery ? 'Hide query' : 'Show query'}
          </button>
        )}
        {showQuery && step && (
          <pre className="mt-1 p-2 bg-red-100 rounded text-[10px] overflow-x-auto whitespace-pre-wrap">{step.query}</pre>
        )}
      </div>
    )
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      {/* Header */}
      <div className={`px-2.5 py-1.5 bg-gray-50 border-b border-gray-200 ${collapsed ? 'cursor-pointer' : ''}`}
        onClick={collapsed ? () => setExpanded(!expanded) : undefined}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {collapsed && (
              <span className="text-[10px] text-gray-400">{expanded ? '▼' : '▶'}</span>
            )}
            <span className="text-xs">{sourceIcon}</span>
            <span className="text-xs font-medium text-gray-700">{source.alias}</span>
            <span className="text-[10px] text-gray-400">({sourceLabel})</span>
          </div>
          <div className="flex items-center gap-2">
            {source.row_count !== undefined && (
              <span className="text-[10px] text-gray-500">
                {source.row_count} row{source.row_count !== 1 ? 's' : ''}
                {source.truncated && ' (truncated)'}
              </span>
            )}
            {source.bytes_processed !== undefined && (
              <span className="text-[10px] text-gray-400">
                {formatBytes(source.bytes_processed)}
              </span>
            )}
          </div>
        </div>

        {/* SQL toggle button - full width, always visible */}
        {expanded && step && (
          <button
            onClick={() => setShowQuery(!showQuery)}
            className="mt-1.5 w-full flex items-center justify-center gap-1 px-2 py-1 text-[11px] font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded hover:bg-blue-100 transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
            {showQuery ? 'Hide SQL Query' : 'View SQL Query'}
          </button>
        )}
      </div>

      {/* SQL Query (collapsible) */}
      {expanded && showQuery && step && (
        <div className="px-2.5 py-2 bg-gray-900 border-b border-gray-200">
          <pre className="text-[11px] text-green-400 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">{step.query}</pre>
        </div>
      )}

      {/* Results table — preview capped at 50 rows for display */}
      {expanded && source.columns && source.rows && source.rows.length > 0 ? (
        <>
          {source.rows.length > PREVIEW_ROWS && (
            <div className="px-2.5 py-1.5 bg-amber-50 border-b border-amber-200">
              <p className="text-[10px] text-amber-700">
                Showing {PREVIEW_ROWS} of {source.row_count?.toLocaleString() || source.rows.length.toLocaleString()} rows. Full dataset was used for the merged result above.
              </p>
            </div>
          )}
          <div className="overflow-x-auto max-h-60">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50">
                  {source.columns.map((col) => (
                    <th
                      key={col}
                      className="px-2 py-1 text-left font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {source.rows.slice(0, PREVIEW_ROWS).map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}
                  >
                    {row.map((cell, cellIdx) => (
                      <td
                        key={cellIdx}
                        className="px-2 py-1 text-gray-700 border-b border-gray-100 whitespace-nowrap max-w-[200px] truncate"
                        title={cell != null ? String(cell) : 'NULL'}
                      >
                        {cell != null ? String(cell) : <span className="text-gray-400 italic">NULL</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : expanded ? (
        <div className="px-2.5 py-3 text-xs text-gray-500 text-center">No results</div>
      ) : null}
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
