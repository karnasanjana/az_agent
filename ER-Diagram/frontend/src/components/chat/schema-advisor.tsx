'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import ChatMessage from './chat-message'
import ChatInput from './chat-input'
import { useSession } from 'next-auth/react'
import type { ChatMessage as ChatMessageType, Suggestion, DataSource } from '@/types/chat'
import type { DatabaseSchema } from '@/types/schema'
import { applySuggestion, cloneSchema, getAffectedTables } from '@/lib/schema-diff'
import { getApiBaseUrl } from '@/app/actions'

const MAX_UNDO = 10

interface SchemaAdvisorProps {
  isOpen: boolean
  onToggle: () => void
  schema: DatabaseSchema
  onSchemaChange: (newSchema: DatabaseSchema) => void
  onHighlightTables: (tableNames: Set<string> | null) => void
  onEnterPreview?: (totalSuggestions: number) => void
}

function getDataSources(sessionAccessToken?: string): DataSource[] {
  const sources: DataSource[] = []

  // BigQuery: project_id must be the GCP project, not the dataset name
  const projectId = sessionStorage.getItem('bq_project_id') || ''
  const accessToken = sessionAccessToken || sessionStorage.getItem('bq_access_token') || ''

  if (projectId && accessToken) {
    sources.push({
      type: 'bigquery',
      project_id: projectId,
      access_token: accessToken,
    })
  }

  // SQL Server: credentials stored in sessionStorage during connection
  try {
    const creds = JSON.parse(sessionStorage.getItem('db_credentials') || '{}')
    if (creds.host) {
      // postgres + sqlserver share the db_credentials key; db_type tells them apart.
      const dbType = sessionStorage.getItem('db_type') === 'postgres' ? 'postgres' : 'sqlserver'
      sources.push({
        type: dbType,
        host: creds.host,
        port: creds.port || (dbType === 'postgres' ? 5432 : 1433),
        database: creds.database,
        username: creds.username,
        password: creds.password,
      })
    }
  } catch {
    // ignore
  }

  // Dataverse
  const dvEnvUrl = sessionStorage.getItem('dv_environment_url') || ''
  const dvToken = sessionStorage.getItem('dv_access_token') || ''
  if (dvEnvUrl && dvToken) {
    sources.push({ type: 'dataverse', environment_url: dvEnvUrl, access_token: dvToken })
  }

  return sources
}

export default function SchemaAdvisor({
  isOpen,
  onToggle,
  schema,
  onSchemaChange,
  onHighlightTables,
  onEnterPreview,
}: SchemaAdvisorProps) {
  const { data: session } = useSession()
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [undoStack, setUndoStack] = useState<DatabaseSchema[]>([])
  const [apiBase, setApiBase] = useState<string>('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    getApiBaseUrl().then(setApiBase)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const buildHistory = useCallback(() => {
    return messages
      .filter((m) => !m.isStreaming)
      .map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
  }, [messages])

  const handleSend = useCallback(
    async (userMessage: string) => {
      const userMsg: ChatMessageType = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: userMessage,
      }

      const assistantMsgId = `assistant-${Date.now()}`
      const assistantMsg: ChatMessageType = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        isStreaming: true,
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsLoading(true)

      try {
        const history = buildHistory()
        const sessionToken = (session as any)?.accessToken as string | undefined
        const dataSources = getDataSources(sessionToken)

        const response = await fetch(`${apiBase}/api/chat/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userMessage,
            schema,
            history,
            data_sources: dataSources,
          }),
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || `Server error: ${response.status}`)
        }

        const data = await response.json()

        if (data.type === 'data') {
          // Data query response
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: data.explanation || 'Query executed.',
                    isStreaming: false,
                    queryPlan: data.query_plan || [],
                    queryResults: data.query_results || undefined,
                  }
                : m
            )
          )
        } else if (data.type === 'clarification') {
          // Clarification questions with clickable options
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: data.explanation || '',
                    isStreaming: false,
                    clarifications: data.questions || [],
                  }
                : m
            )
          )
        } else {
          // Schema advice response
          const suggestions: Suggestion[] = (data.suggestions || []).map((s: Suggestion) => ({
            ...s,
            status: 'pending' as const,
          }))

          // Enter preview mode if there are suggestions
          if (suggestions.length > 0 && onEnterPreview) {
            onEnterPreview(suggestions.length)
          }

          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, content: data.explanation || 'No response', isStreaming: false, suggestions }
                : m
            )
          )
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `Failed to get response: ${errorMessage}`, isStreaming: false }
              : m
          )
        )
      } finally {
        setIsLoading(false)
      }
    },
    [schema, buildHistory, apiBase, session]
  )

  const handleAcceptSuggestion = useCallback(
    (suggestion: Suggestion) => {
      setUndoStack((prev) => {
        const newStack = [...prev, cloneSchema(schema)]
        return newStack.slice(-MAX_UNDO)
      })

      const newSchema = applySuggestion(schema, suggestion)
      onSchemaChange(newSchema)

      setMessages((prev) =>
        prev.map((m) => ({
          ...m,
          suggestions: m.suggestions?.map((s) =>
            s.id === suggestion.id ? { ...s, status: 'accepted' as const } : s
          ),
        }))
      )

      onHighlightTables(null)
    },
    [schema, onSchemaChange, onHighlightTables]
  )

  const handleSkipSuggestion = useCallback(
    (suggestion: Suggestion) => {
      setMessages((prev) =>
        prev.map((m) => ({
          ...m,
          suggestions: m.suggestions?.map((s) =>
            s.id === suggestion.id ? { ...s, status: 'skipped' as const } : s
          ),
        }))
      )
      onHighlightTables(null)
    },
    [onHighlightTables]
  )

  const handlePreviewSuggestion = useCallback(
    (suggestion: Suggestion) => {
      const affected = getAffectedTables(suggestion)
      onHighlightTables(affected)
    },
    [onHighlightTables]
  )

  const handleClearPreview = useCallback(() => {
    onHighlightTables(null)
  }, [onHighlightTables])

  const handleSelectClarification = useCallback(
    (_questionId: string, answer: string) => {
      handleSend(answer)
    },
    [handleSend]
  )

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0) return
    const previousSchema = undoStack[undoStack.length - 1]
    setUndoStack((prev) => prev.slice(0, -1))
    onSchemaChange(previousSchema)
  }, [undoStack, onSchemaChange])

  if (!isOpen) return null

  return (
    <div className="w-96 h-full flex flex-col bg-white border-l border-gray-200 shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50 flex-shrink-0">
        <div className="flex items-center gap-2">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-600">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <h3 className="font-semibold text-gray-900 text-sm">Schema Advisor</h3>
        </div>
        <div className="flex items-center gap-1">
          {undoStack.length > 0 && (
            <button
              onClick={handleUndo}
              className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition-colors"
              title={`Undo (${undoStack.length})`}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
            </button>
          )}
          <button
            onClick={onToggle}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition-colors"
            title="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center mx-auto mb-3">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-600">
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <h4 className="font-medium text-gray-900 mb-1">Schema Advisor</h4>
            <p className="text-xs text-gray-500 mb-4">Ask about schema or query your data</p>
            <div className="space-y-2">
              {[
                'How can I optimize this schema?',
                'Can you suggest missing relationships?',
                'How many records are in each table?',
                'Show me a sample of data from the largest table',
              ].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => handleSend(prompt)}
                  disabled={isLoading}
                  className="w-full text-left px-3 py-2 text-xs text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700 transition-colors disabled:opacity-50"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            onAcceptSuggestion={handleAcceptSuggestion}
            onSkipSuggestion={handleSkipSuggestion}
            onPreviewSuggestion={handlePreviewSuggestion}
            onSelectClarification={handleSelectClarification}
            onClearPreview={handleClearPreview}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isLoading} />
    </div>
  )
}
