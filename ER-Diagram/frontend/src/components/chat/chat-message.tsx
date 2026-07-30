'use client'

import ReactMarkdown from 'react-markdown'
import type { ChatMessage as ChatMessageType, Suggestion, WorkflowStep } from '@/types/chat'
import SuggestionCard from './suggestion-card'
import ClarificationGroup from './clarification-card'
import QueryResult from './query-result'
import AgentWorkflow from './agent-workflow'

interface ChatMessageProps {
  message: ChatMessageType
  onAcceptSuggestion: (suggestion: Suggestion) => void
  onSkipSuggestion: (suggestion: Suggestion) => void
  onPreviewSuggestion: (suggestion: Suggestion) => void
  onClearPreview: () => void
  onSelectClarification?: (questionId: string, answer: string) => void
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-2 py-1">
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
    </div>
  )
}

export default function ChatMessage({
  message,
  onAcceptSuggestion,
  onSkipSuggestion,
  onPreviewSuggestion,
  onClearPreview,
  onSelectClarification,
}: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isEmpty = !message.content && message.isStreaming
  const hasDataWorkflow = !isUser && message.queryResults?.workflow && message.queryPlan

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[95%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
            : 'glass-panel bg-slate-900/60 text-slate-200 border border-slate-700/80 shadow-sm'
        }`}
      >
        {/* Typing indicator when streaming with no content yet */}
        {isEmpty && <TypingIndicator />}

        {/* Message content — hide for data responses (plan goes in workflow, summary goes after result) */}
        {message.content && !hasDataWorkflow && (
          <div className="break-words">
            {isUser ? (
              <span className="whitespace-pre-wrap">{message.content}</span>
            ) : (
              <div className="prose prose-sm prose-slate max-w-none text-slate-200
                prose-headings:text-slate-100 prose-headings:font-semibold
                prose-h2:text-sm prose-h2:mt-3 prose-h2:mb-1
                prose-h3:text-xs prose-h3:mt-2 prose-h3:mb-1
                prose-h4:text-xs prose-h4:mt-1.5 prose-h4:mb-0.5
                prose-p:text-sm prose-p:my-1 prose-p:leading-relaxed
                prose-li:text-sm prose-li:my-0.5
                prose-strong:text-slate-100
                prose-code:text-xs prose-code:bg-slate-800 prose-code:text-indigo-300 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
                prose-pre:bg-[#0d1117] prose-pre:text-slate-300 prose-pre:text-xs prose-pre:rounded-md prose-pre:my-2 prose-pre:border prose-pre:border-slate-800
                prose-hr:my-2 prose-hr:border-slate-700
                prose-ul:my-1 prose-ol:my-1
              ">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
            {message.isStreaming && (
              <span className="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse" />
            )}
          </div>
        )}

        {/* Streaming indicator for data responses */}
        {message.isStreaming && hasDataWorkflow && (
          <span className="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse" />
        )}

        {/* Live workflow steps (while streaming) */}
        {message.liveWorkflowSteps && message.liveWorkflowSteps.length > 0 && !message.queryResults && (
          <LiveWorkflowSteps steps={message.liveWorkflowSteps} />
        )}

        {/* Query results — use AgentWorkflow if workflow data available, otherwise fallback to QueryResult */}
        {message.queryPlan && message.queryResults && message.queryResults.sources && (
          message.queryResults.workflow ? (
            <AgentWorkflow
              steps={message.queryResults.workflow.steps}
              totalTime={message.queryResults.workflow.total_time}
              sources={message.queryResults.sources}
              merged={message.queryResults.merged}
              queryPlan={message.queryPlan}
              planDescription={message.planDescription}
              summary={message.content}
            />
          ) : (
            <QueryResult
              queryPlan={message.queryPlan}
              sources={message.queryResults.sources}
              merged={message.queryResults.merged}
            />
          )
        )}

        {/* Clarification questions */}
        {message.clarifications && message.clarifications.length > 0 && onSelectClarification && (
          <ClarificationGroup
            questions={message.clarifications}
            onSubmitAll={(combined) => onSelectClarification('all', combined)}
          />
        )}

        {/* Suggestions */}
        {message.suggestions && message.suggestions.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.suggestions.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onAccept={onAcceptSuggestion}
                onSkip={onSkipSuggestion}
                onPreview={onPreviewSuggestion}
                onClearPreview={onClearPreview}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function LiveWorkflowSteps({ steps }: { steps: WorkflowStep[] }) {
  return (
    <div className="mt-3 border border-slate-700/80 rounded-lg bg-slate-900/40 backdrop-blur-sm overflow-hidden">
      <div className="px-3 py-2 bg-slate-800/80 border-b border-slate-700/80 flex items-center gap-2">
        <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs font-semibold text-slate-200">Agent Working...</span>
      </div>
      <div className="divide-y divide-slate-700/50">
        {steps.map((step, idx) => (
          <div key={idx} className="px-3 py-2 flex items-center gap-2.5 animate-fadeIn">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
              step.status === 'success'
                ? 'bg-emerald-900/30 text-emerald-400'
                : step.status === 'error'
                ? 'bg-red-900/30 text-red-400'
                : step.status === 'fixing'
                ? 'bg-amber-900/30 text-amber-400'
                : step.status === 'retrying'
                ? 'bg-amber-900/20 text-amber-300'
                : 'bg-slate-800'
            }`}>
              {step.status === 'running' || step.status === 'retrying' ? (
                <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              ) : step.status === 'fixing' ? (
                <div className="w-3 h-3 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
              ) : step.status === 'success' ? (
                <span className="text-[10px]">✓</span>
              ) : (
                <span className="text-[10px]">✗</span>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-slate-200">
                  {step.type === 'planning' ? 'Planning' : step.type === 'merge' ? 'Merge' : step.alias || 'Query'}
                </span>
                {step.source && (
                  <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                    step.source === 'bigquery' ? 'bg-blue-900/40 text-blue-300 border border-blue-500/30' : 'bg-orange-900/40 text-orange-300 border border-orange-500/30'
                  }`}>
                    {step.source === 'bigquery' ? 'BigQuery' : 'SQL Server'}
                  </span>
                )}
              </div>
              {step.description && (
                <p className="text-[10px] text-slate-400 truncate">{step.description}</p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {step.rows !== undefined && (
                <span className="text-[10px] text-slate-500">{step.rows.toLocaleString()} rows</span>
              )}
              {step.time !== undefined && (
                <span className="text-[10px] text-slate-500 font-mono">{step.time}s</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
