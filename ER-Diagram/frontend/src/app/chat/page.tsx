'use client'

import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useSession } from 'next-auth/react'
import ChatMessage from '@/components/chat/chat-message'
import ChatInput from '@/components/chat/chat-input'
import UserMenu from '@/components/user-menu'
import { Toolbar } from '@/components/diagram/toolbar'
import { ZionLogo } from '@/components/zion-logo'
import { applySuggestion, cloneSchema, getAffectedTables } from '@/lib/schema-diff'
import { getApiBaseUrl } from '@/app/actions'
import type { ChatMessage as ChatMessageType, Suggestion, DataSource } from '@/types/chat'
import type { DatabaseSchema } from '@/types/schema'

const MAX_UNDO = 10
const CHAT_HISTORY_KEY = 'chat_messages'

function getDataSources(sessionAccessToken?: string): DataSource[] {
  const sources: DataSource[] = []
  // BigQuery project_id must be the GCP project, not the dataset name
  const projectId = sessionStorage.getItem('bq_project_id') || ''
  const accessToken = sessionAccessToken || sessionStorage.getItem('bq_access_token') || ''
  if (projectId && accessToken) {
    sources.push({ type: 'bigquery', project_id: projectId, access_token: accessToken })
  }
  try {
    const creds = JSON.parse(sessionStorage.getItem('db_credentials') || '{}')
    if (creds.host) {
      // postgres + sqlserver share the db_credentials key; db_type tells them apart.
      const dbType = sessionStorage.getItem('db_type') === 'postgres' ? 'postgres' : 'sqlserver'
      sources.push({
        type: dbType, host: creds.host, port: creds.port || (dbType === 'postgres' ? 5432 : 1433),
        database: creds.database, username: creds.username, password: creds.password,
      })
    }
  } catch { /* ignore */ }
  // Dataverse
  const dvEnvUrl = sessionStorage.getItem('dv_environment_url') || ''
  const dvToken = sessionStorage.getItem('dv_access_token') || ''
  if (dvEnvUrl && dvToken) {
    sources.push({ type: 'dataverse', environment_url: dvEnvUrl, access_token: dvToken })
  }
  return sources
}

export default function ChatPage() {
  const { data: session } = useSession()
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [undoStack, setUndoStack] = useState<DatabaseSchema[]>([])
  const [apiBase, setApiBase] = useState('')
  const [changeCount, setChangeCount] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Load schema and chat history on mount
  useEffect(() => {
    getApiBaseUrl().then(setApiBase)
    const stored = sessionStorage.getItem('extracted_schema')
    if (stored) {
      try { setSchema(JSON.parse(stored)) } catch { /* ignore */ }
    }
    const storedMessages = sessionStorage.getItem(CHAT_HISTORY_KEY)
    if (storedMessages) {
      try { setMessages(JSON.parse(storedMessages)) } catch { /* ignore */ }
    }
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Persist chat messages (strip heavy query results to avoid sessionStorage quota)
  useEffect(() => {
    if (messages.length > 0) {
      const light = messages.map((m) => {
        if (m.queryResults || m.queryPlan || m.planDescription || m.liveWorkflowSteps) {
          const { queryResults, queryPlan, planDescription, liveWorkflowSteps, ...rest } = m
          return rest
        }
        return m
      })
      try {
        sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(light))
      } catch {
        // Storage full — clear old messages and keep recent ones
        sessionStorage.removeItem(CHAT_HISTORY_KEY)
      }
    }
  }, [messages])

  const buildHistory = useCallback(() => {
    return messages
      .filter((m) => !m.isStreaming)
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
  }, [messages])

  const handleSend = useCallback(
    async (userMessage: string) => {
      if (!schema) return

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

        const response = await fetch(`${apiBase}/api/chat/stream`, {
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

        // Read SSE stream
        const reader = response.body?.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = 'step' // Persists across chunks

        if (!reader) throw new Error('No response stream')

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim()
              continue
            }
            if (!line.startsWith('data:')) continue
            const jsonStr = line.slice(5).trim()
            if (!jsonStr) continue

            let parsed
            try { parsed = JSON.parse(jsonStr) } catch { continue }

            const eventType = currentEvent
            currentEvent = 'step' // reset after consuming

            if (eventType === 'step') {
              // Real-time workflow step update
              const step = parsed as import('@/types/chat').WorkflowStep
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsgId) return m
                  const existing = m.liveWorkflowSteps || []
                  const updated = step.status === 'running' || step.status === 'retrying' || step.status === 'fixing'
                    ? [...existing, step]
                    : existing.map((s) =>
                        s.type === step.type && s.alias === step.alias && (s.status === 'running' || s.status === 'retrying' || s.status === 'fixing')
                          ? step : s
                      ).concat(
                        existing.some((s) => s.type === step.type && s.alias === step.alias) ? [] : [step]
                      )
                  return { ...m, liveWorkflowSteps: updated }
                })
              )
            } else if (eventType === 'result') {
              // Final result — replace live steps with full response
              const data = parsed
              if (data.type === 'data') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? {
                          ...m,
                          content: data.explanation || '',
                          planDescription: data.plan_description || '',
                          isStreaming: false,
                          liveWorkflowSteps: undefined,
                          queryPlan: data.query_plan || [],
                          queryResults: data.query_results || undefined,
                        }
                      : m
                  )
                )
              } else if (data.type === 'clarification') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: data.explanation || '', isStreaming: false, liveWorkflowSteps: undefined, clarifications: data.questions || [] }
                      : m
                  )
                )
              } else {
                const suggestions: Suggestion[] = (data.suggestions || []).map((s: Suggestion) => ({
                  ...s, status: 'pending' as const,
                }))
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: data.explanation || 'No response', isStreaming: false, liveWorkflowSteps: undefined, suggestions }
                      : m
                  )
                )
              }
            } else if (eventType === 'error') {
              throw new Error(parsed.error || 'Stream error')
            }
          }
        }

        // Ensure streaming is off if we didn't get a result event
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId && m.isStreaming
              ? { ...m, isStreaming: false, content: m.content || 'No response received.' }
              : m
          )
        )
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error'
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: `Failed to get response: ${errorMessage}`, isStreaming: false, liveWorkflowSteps: undefined }
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
      if (!schema) return

      setUndoStack((prev) => {
        const newStack = [...prev, cloneSchema(schema)]
        return newStack.slice(-MAX_UNDO)
      })

      const newSchema = applySuggestion(schema, suggestion)
      setSchema(newSchema)
      sessionStorage.setItem('extracted_schema', JSON.stringify(newSchema))
      setChangeCount((prev) => prev + 1)

      setMessages((prev) =>
        prev.map((m) => ({
          ...m,
          suggestions: m.suggestions?.map((s) =>
            s.id === suggestion.id ? { ...s, status: 'accepted' as const } : s
          ),
        }))
      )
    },
    [schema]
  )

  const handleSkipSuggestion = useCallback((suggestion: Suggestion) => {
    setMessages((prev) =>
      prev.map((m) => ({
        ...m,
        suggestions: m.suggestions?.map((s) =>
          s.id === suggestion.id ? { ...s, status: 'skipped' as const } : s
        ),
      }))
    )
  }, [])

  const handlePreviewSuggestion = useCallback((_suggestion: Suggestion) => {
    // No canvas highlighting on full-page chat
  }, [])

  const handleClearPreview = useCallback(() => {}, [])

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
    setSchema(previousSchema)
    sessionStorage.setItem('extracted_schema', JSON.stringify(previousSchema))
    setChangeCount((prev) => Math.max(0, prev - 1))
  }, [undoStack])

  const handleReset = useCallback(() => {
    setMessages([])
    sessionStorage.removeItem(CHAT_HISTORY_KEY)
  }, [])

  const totalRelationships = schema?.foreign_keys.length || 0

  const chatToolbarItems = useMemo(() => [
    {
      id: 'view-diagram',
      label: 'View Diagram',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagram' },
    },
    {
      id: 'add-dataset',
      label: 'Add Data Source',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagram' },
    },
    {
      id: 'view-sql',
      label: 'View SQL',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagram' },
    },
    {
      id: 'relationships',
      label: 'Relationships',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagram' },
      badge: totalRelationships || undefined,
    },
    {
      id: 'ai-advisor',
      label: 'Talk to your Data',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      ),
      onClick: () => {},
      active: true,
    },
    {
      id: 'my-diagrams',
      label: 'My Diagrams',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagrams' },
    },
    {
      id: 'start-over',
      label: 'Start Over',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="1 4 1 10 7 10" />
          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
        </svg>
      ),
      onClick: () => { window.location.href = '/' },
    },
  ], [totalRelationships])

  if (!schema) {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">No schema loaded. Connect to a database first.</p>
          <a href="/" className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
            Connect to Database
          </a>
        </div>
      </main>
    )
  }

  return (
    <main className="h-screen flex flex-col bg-gradient-surface">
      {/* Header */}
      <header className="glass-panel text-white px-6 py-3 flex items-center justify-between flex-shrink-0 border-b border-slate-700/80">
        <div className="flex items-center gap-4">
          <div className="border-r border-slate-700/80 pr-4">
            <ZionLogo className="h-7 text-white drop-shadow-[0_0_15px_rgba(79,70,229,0.4)]" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide">Talk to your Data</h1>
            <p className="text-xs text-white/60 mt-0.5">
              {schema.table_count} tables, {schema.foreign_keys.length} relationships
              {changeCount > 0 && (
                <span className="ml-2 text-indigo-300 font-medium">
                  ({changeCount} change{changeCount !== 1 ? 's' : ''} applied)
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {undoStack.length > 0 && (
            <button
              onClick={handleUndo}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-white/80 border border-white/20 rounded-lg hover:bg-white/10 transition-colors"
              title={`Undo (${undoStack.length})`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1 4 1 10 7 10" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
              Undo
            </button>
          )}
          <button
            onClick={handleReset}
            className="p-1.5 text-white/50 hover:text-white rounded transition-colors"
            title="Clear chat"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>
          <UserMenu />
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Shared sidebar — same as diagram page */}
        <Toolbar items={chatToolbarItems} />

        {/* Right panel: chat + input */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto chat-scroll">
            <div className="w-full px-6 py-6 space-y-4">
          {/* Empty state */}
          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="w-16 h-16 rounded-2xl bg-indigo-900/50 border border-indigo-500/30 flex items-center justify-center mx-auto mb-5 drop-shadow-lg">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-400">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h2 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400 mb-2 tracking-tight">Talk to your Data</h2>
              <p className="text-slate-400 mb-10 max-w-md mx-auto">
                Understand your databases, explore relationships, and ask questions about your data.
              </p>
              <div className="grid grid-cols-2 gap-3 max-w-lg mx-auto">
                {[
                  { text: 'What does this database do?', icon: '?' },
                  { text: 'Explain the key relationships', icon: '~' },
                  { text: 'Which tables have the most data?', icon: '#' },
                  { text: 'Show me sample customer orders', icon: '>' },
                ].map(({ text, icon }) => (
                  <button
                    key={text}
                    onClick={() => handleSend(text)}
                    disabled={isLoading}
                    className="text-left px-4 py-3.5 text-sm text-slate-300 glass-panel bg-slate-900/60 border border-slate-700 rounded-xl hover:bg-slate-800 hover:border-indigo-500/50 hover:text-indigo-300 hover:shadow-[0_0_15px_rgba(79,70,229,0.2)] transition-all disabled:opacity-50 shadow-sm group"
                  >
                    <span className="text-indigo-400 font-mono mr-2 group-hover:text-indigo-600">{icon}</span>
                    {text}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Messages */}
          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              onAcceptSuggestion={handleAcceptSuggestion}
              onSkipSuggestion={handleSkipSuggestion}
              onPreviewSuggestion={handlePreviewSuggestion}
              onClearPreview={handleClearPreview}
              onSelectClarification={handleSelectClarification}
            />
          ))}
            <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="flex-shrink-0">
            <div className="w-full px-6">
              <ChatInput onSend={handleSend} disabled={isLoading} />
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
