'use client'

import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { WorkflowStep, QuerySourceResult, QueryStep } from '@/types/chat'

const PREVIEW_ROWS = 50

interface AgentWorkflowProps {
  steps: WorkflowStep[]
  totalTime: number
  sources: QuerySourceResult[]
  merged?: QuerySourceResult
  queryPlan: QueryStep[]
  planDescription?: string
  summary?: string
}

export default function AgentWorkflow({
  steps,
  totalTime,
  sources,
  merged,
  queryPlan,
  planDescription,
  summary,
}: AgentWorkflowProps) {
  const [workflowOpen, setWorkflowOpen] = useState(false)

  return (
    <div className="mt-3 space-y-3">
      {/* 1. Agent Workflow — collapsable */}
      <div className="border border-gray-200 rounded-lg bg-gray-50/50 overflow-hidden">
        <button
          type="button"
          onClick={() => setWorkflowOpen(!workflowOpen)}
          className="w-full px-3 py-2 bg-gray-100/80 border-b border-gray-200 flex items-center justify-between hover:bg-gray-100 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400">{workflowOpen ? '▼' : '▶'}</span>
            <div className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center">
              <svg className="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
            </div>
            <span className="text-xs font-semibold text-gray-700">Agent Workflow</span>
            <span className="text-[10px] text-gray-400">
              {steps.length} step{steps.length !== 1 ? 's' : ''}
            </span>
          </div>
          <span className="text-[10px] text-gray-400 font-mono">{totalTime}s</span>
        </button>

        {workflowOpen && (
          <div className="divide-y divide-gray-100">
            {steps.map((step, idx) => (
              <StepRow
                key={idx}
                step={step}
                source={step.type === 'query' ? sources.find((s) => s.alias === step.alias) : undefined}
                queryStep={step.type === 'query' ? queryPlan.find((q) => q.alias === step.alias) : undefined}
                isLast={idx === steps.length - 1}
              />
            ))}
          </div>
        )}
      </div>

      {/* 2. Result table — merged result for cross-DB, or single source result */}
      {merged && !merged.error ? (
        <MergedResultCard source={merged} isMerge />
      ) : !merged && sources.length > 0 && sources.some((s) => s.rows && s.rows.length > 0 && !s.error) && (
        (() => {
          // For single-database queries, show the first successful source as the result
          const successSources = sources.filter((s) => s.rows && s.rows.length > 0 && !s.error)
          return successSources.length === 1 ? (
            <MergedResultCard source={successSources[0]} />
          ) : (
            // Multiple single-DB sources (no merge) — show each
            <div className="space-y-3">
              {successSources.map((s) => (
                <MergedResultCard key={s.alias} source={s} label={s.alias} />
              ))}
            </div>
          )
        })()
      )}

      {/* 3. Result summary from Haiku */}
      {summary && (
        <div className="px-1">
          <div className="prose prose-sm prose-gray max-w-none
            prose-p:text-sm prose-p:my-1 prose-p:leading-relaxed
            prose-strong:text-gray-900
          ">
            <ReactMarkdown>{summary}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}

function StepRow({
  step,
  source,
  queryStep,
  isLast,
}: {
  step: WorkflowStep
  source?: QuerySourceResult
  queryStep?: QueryStep
  isLast: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const isExpandable = step.type === 'query' || step.type === 'planning'

  return (
    <div className="animate-fadeIn">
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        disabled={!isExpandable}
        className={`w-full px-3 py-2 flex items-start gap-2.5 text-left transition-colors ${
          isExpandable ? 'hover:bg-gray-50 cursor-pointer' : ''
        }`}
      >
        {/* Timeline dot */}
        <div className="flex flex-col items-center flex-shrink-0 pt-0.5">
          <StepIcon step={step} />
          {!isLast && <div className="w-px h-3 bg-gray-200 mt-0.5" />}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-xs font-medium text-gray-800 truncate">
                {stepLabel(step)}
              </span>
              {step.source && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                  step.source === 'bigquery' ? 'bg-blue-50 text-blue-600' :
                  step.source === 'dataverse' ? 'bg-purple-50 text-purple-600' :
                  'bg-orange-50 text-orange-600'
                }`}>
                  {step.source === 'bigquery' ? 'BigQuery' : step.source === 'dataverse' ? 'Dataverse' : 'SQL Server'}
                </span>
              )}
              {isExpandable && (
                <span className="text-[10px] text-gray-400">{expanded ? '▼' : '▶'}</span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {step.rows !== undefined && (
                <span className="text-[10px] text-gray-500">
                  {step.rows.toLocaleString()} row{step.rows !== 1 ? 's' : ''}
                </span>
              )}
              {step.time !== undefined && (
                <span className="text-[10px] text-gray-400 font-mono">{step.time}s</span>
              )}
            </div>
          </div>
          {/* Short description for non-planning steps */}
          {step.type !== 'planning' && step.description && (
            <p className="text-[10px] text-gray-500 mt-0.5 truncate">{step.description}</p>
          )}
          {step.error && (
            <p className="text-[10px] text-red-500 mt-0.5">{step.error}</p>
          )}
        </div>
      </button>

      {/* Expanded: Planning description */}
      {expanded && step.type === 'planning' && step.description && (
        <div className="mx-3 mb-2 px-3 py-2 bg-indigo-50/50 border border-indigo-100 rounded-md">
          <div className="prose prose-sm prose-gray max-w-none prose-p:text-xs prose-p:my-0.5 prose-p:text-gray-600 prose-li:text-xs prose-li:my-0 prose-strong:text-gray-700 prose-ul:my-0.5 prose-ol:my-0.5 prose-h3:text-xs prose-h3:mt-1 prose-h3:mb-0.5">
            <ReactMarkdown>{step.description}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Expanded: SQL query + data preview */}
      {expanded && step.type === 'query' && (
        <div className="mx-3 mb-2 border border-gray-200 rounded-md overflow-hidden">
          {queryStep && (
            <div className="px-2.5 py-2 bg-gray-900">
              <pre className="text-[10px] text-green-400 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">
                {queryStep.query}
              </pre>
            </div>
          )}
          {source && source.columns && source.rows && source.rows.length > 0 && (
            <>
              {source.rows.length > PREVIEW_ROWS && (
                <div className="px-2 py-1 bg-amber-50 border-t border-amber-200">
                  <p className="text-[9px] text-amber-700">
                    Showing {PREVIEW_ROWS} of {source.row_count?.toLocaleString()} rows.
                    {' '}Full dataset was used for the merged result.
                  </p>
                </div>
              )}
              <div className="overflow-x-auto max-h-48 border-t border-gray-200">
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="bg-gray-50">
                      {source.columns.map((col) => (
                        <th key={col} className="px-1.5 py-1 text-left font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {source.rows.slice(0, PREVIEW_ROWS).map((row, rowIdx) => (
                      <tr key={rowIdx} className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx} className="px-1.5 py-0.5 text-gray-600 border-b border-gray-50 whitespace-nowrap max-w-[150px] truncate">
                            {cell != null ? String(cell) : <span className="text-gray-300">NULL</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function MergedResultCard({ source, isMerge, label }: { source: QuerySourceResult; isMerge?: boolean; label?: string }) {
  return (
    <div className="border-2 border-green-300 rounded-lg overflow-hidden bg-white">
      <div className="px-3 py-2 bg-green-50 border-b border-green-200 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-full bg-green-100 flex items-center justify-center">
            <svg className="w-3 h-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          </div>
          <span className="text-xs font-semibold text-green-800">
            {label ? `Result: ${label}` : 'Result'}
          </span>
          {isMerge && (
            <span className="text-[10px] text-green-600">(cross-database merge)</span>
          )}
        </div>
        {source.row_count !== undefined && (
          <span className="text-[10px] text-green-600 font-medium">
            {source.row_count} row{source.row_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>
      {source.columns && source.rows && source.rows.length > 0 ? (
        <div className="overflow-x-auto max-h-72">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-green-50/50">
                {source.columns.map((col) => (
                  <th key={col} className="px-2 py-1.5 text-left font-semibold text-green-800 border-b border-green-200 whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {source.rows.map((row, rowIdx) => (
                <tr key={rowIdx} className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-green-50/20'}>
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
        <div className="px-3 py-4 text-xs text-gray-500 text-center">No results after merge</div>
      )}
    </div>
  )
}

function StepIcon({ step }: { step: WorkflowStep }) {
  const isRunning = step.status === 'running' || step.status === 'retrying'
  const isFixing = step.status === 'fixing'

  if (isRunning) {
    return (
      <div className="w-5 h-5 rounded-full bg-blue-50 flex items-center justify-center">
        <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }
  if (isFixing) {
    return (
      <div className="w-5 h-5 rounded-full bg-amber-100 flex items-center justify-center">
        <div className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const bgColor = step.status === 'success' ? 'bg-green-100 text-green-600'
    : step.status === 'error' ? 'bg-red-100 text-red-600'
    : 'bg-gray-100 text-gray-500'

  return (
    <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${bgColor}`}>
      {step.status === 'success' ? '✓' : step.status === 'error' ? '✗' : '?'}
    </div>
  )
}

function stepLabel(step: WorkflowStep): string {
  switch (step.type) {
    case 'planning': return 'Planning'
    case 'query': return step.alias || 'Query'
    case 'merge': return 'Merge'
    case 'summarizing': return 'Summarizing'
    default: return 'Step'
  }
}
