'use client'

import { useState } from 'react'
import type { DatabaseSchema } from '@/types/schema'
import type { ImpactAnalysisResult } from '@/types/diagram'
import { analyzeImpact } from '@/app/actions'

interface ImpactAnalysisPanelProps {
  isOpen: boolean
  onClose: () => void
  schema: DatabaseSchema | null
}

export function ImpactAnalysisPanel({ isOpen, onClose, schema }: ImpactAnalysisPanelProps) {
  const [selectedTable, setSelectedTable] = useState('')
  const [selectedColumn, setSelectedColumn] = useState('')
  const [result, setResult] = useState<ImpactAnalysisResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const tables = schema?.tables || []
  const selectedTableObj = tables.find(
    (t) => t.table_name === selectedTable
  )

  const handleAnalyze = async () => {
    if (!selectedTable || !schema) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await analyzeImpact(schema, selectedTable, selectedColumn)
      setResult(data as ImpactAnalysisResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setIsLoading(false)
    }
  }

  const riskColors = {
    low: { bg: 'bg-emerald-900/30', border: 'border-emerald-500/30', text: 'text-emerald-400', badge: 'bg-emerald-500/20 text-emerald-400' },
    medium: { bg: 'bg-amber-900/30', border: 'border-amber-500/30', text: 'text-amber-400', badge: 'bg-amber-500/20 text-amber-400' },
    high: { bg: 'bg-red-900/30', border: 'border-red-500/30', text: 'text-red-400', badge: 'bg-red-500/20 text-red-400' },
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-[480px] z-50 glass-panel bg-slate-900/95 border-l border-slate-700 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-200">Impact Analysis</h2>
            <p className="text-xs text-slate-400 mt-0.5">What breaks if you change something?</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Selection */}
        <div className="px-5 py-4 border-b border-slate-800 space-y-3 flex-shrink-0">
          <div className="flex gap-2">
            <select
              value={selectedTable}
              onChange={(e) => {
                setSelectedTable(e.target.value)
                setSelectedColumn('')
                setResult(null)
              }}
              className="flex-1 px-3 py-2.5 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              <option value="">Select table...</option>
              {tables.map((t) => (
                <option key={`${t.schema_name}.${t.table_name}`} value={t.table_name}>
                  {t.schema_name}.{t.table_name}
                </option>
              ))}
            </select>
            {selectedTableObj && (
              <select
                value={selectedColumn}
                onChange={(e) => { setSelectedColumn(e.target.value); setResult(null) }}
                className="w-40 px-3 py-2.5 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                <option value="">Entire table</option>
                {selectedTableObj.columns.map((c) => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
          <button
            onClick={handleAnalyze}
            disabled={!selectedTable || isLoading}
            className="w-full px-4 py-2.5 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)] transition-all disabled:opacity-50 font-medium"
          >
            {isLoading ? 'Analyzing...' : 'Analyze Impact'}
          </button>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {error && (
            <div className="bg-red-900/30 border border-red-500/30 rounded-xl p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {!result && !error && !isLoading && (
            <div className="text-center py-12">
              <svg className="w-12 h-12 mx-auto text-slate-700 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <p className="text-sm text-slate-500">Select a table or column to analyze what would be affected by changes.</p>
            </div>
          )}

          {result && (
            <>
              {/* Risk badge */}
              {result.risk && (
                <div className={`rounded-xl p-4 border ${riskColors[result.risk.level].bg} ${riskColors[result.risk.level].border}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-0.5 text-xs font-bold rounded-full uppercase ${riskColors[result.risk.level].badge}`}>
                      {result.risk.level} risk
                    </span>
                    <span className="text-xs text-slate-500">
                      {result.total_impact_count} dependenc{result.total_impact_count === 1 ? 'y' : 'ies'}
                    </span>
                  </div>
                  <p className={`text-sm ${riskColors[result.risk.level].text}`}>
                    {result.risk.message}
                  </p>
                </div>
              )}

              {/* Direct dependencies */}
              {result.direct_dependencies.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">
                    Direct Dependencies ({result.direct_dependencies.length})
                  </h3>
                  <div className="space-y-2">
                    {result.direct_dependencies.map((dep, i) => (
                      <div key={i} className="bg-slate-800/60 border border-slate-700/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`w-2 h-2 rounded-full ${dep.type === 'referenced_by' ? 'bg-amber-400' : 'bg-indigo-400'}`} />
                          <span className="text-sm font-medium text-slate-300">{dep.table}</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">
                            {dep.type === 'referenced_by' ? 'depends on this' : 'this depends on'}
                          </span>
                        </div>
                        {dep.relationship && (
                          <p className="text-xs text-slate-500 font-mono ml-4">{dep.relationship}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Indirect dependencies */}
              {result.indirect_dependencies.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 mb-2">
                    Indirect Dependencies ({result.indirect_dependencies.length})
                  </h3>
                  <div className="space-y-2">
                    {result.indirect_dependencies.map((dep, i) => (
                      <div key={i} className="bg-slate-800/40 border border-slate-700/30 rounded-lg p-3">
                        <div className="flex items-center gap-2">
                          <span className="w-2 h-2 rounded-full bg-slate-500" />
                          <span className="text-sm text-slate-400">{dep.table}</span>
                          {dep.via && (
                            <span className="text-[10px] text-slate-600">via {dep.via}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.total_impact_count === 0 && (
                <p className="text-sm text-slate-500 text-center py-4">
                  No foreign key dependencies found. This table/column can be safely modified from a referential integrity perspective.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  )
}
