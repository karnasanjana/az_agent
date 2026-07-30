'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useSession } from 'next-auth/react'
import ChatMessage from './chat-message'
import ChatInput from './chat-input'
import { getApiBaseUrl } from '@/app/actions'
import { applySuggestion, cloneSchema } from '@/lib/schema-diff'
import type { ChatMessage as ChatMessageType, Suggestion, DataSource, WorkflowStep } from '@/types/chat'
import type { DatabaseSchema } from '@/types/schema'

const MAX_UNDO = 10

interface FloatingChatProps {
  schema: DatabaseSchema
  onSchemaChange?: (schema: DatabaseSchema) => void
}

function getDataSources(sessionAccessToken?: string): DataSource[] {
  const sources: DataSource[] = []
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

export default function FloatingChat({ schema, onSchemaChange }: FloatingChatProps) {
  const { data: session } = useSession()
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [apiBase, setApiBase] = useState('')
  const [undoStack, setUndoStack] = useState<DatabaseSchema[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  // Draggable position
  const [position, setPosition] = useState({ x: 0, y: 0 }) // offset from default bottom-right
  const dragRef = useRef<{ startX: number; startY: number; startPosX: number; startPosY: number } | null>(null)
  const isDragging = useRef(false)

  const handleDragStart = useCallback((e: React.MouseEvent | React.PointerEvent) => {
    dragRef.current = { startX: e.clientX, startY: e.clientY, startPosX: position.x, startPosY: position.y }
    isDragging.current = false

    const handleMove = (ev: PointerEvent) => {
      if (!dragRef.current) return
      const dx = ev.clientX - dragRef.current.startX
      const dy = ev.clientY - dragRef.current.startY
      if (!isDragging.current && Math.abs(dx) + Math.abs(dy) > 4) {
        isDragging.current = true
      }
      if (isDragging.current) {
        setPosition({ x: dragRef.current.startPosX + dx, y: dragRef.current.startPosY + dy })
      }
    }

    const handleUp = () => {
      // Small delay so click handler can check isDragging
      setTimeout(() => { isDragging.current = false }, 0)
      dragRef.current = null
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
    }

    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
  }, [position])

  useEffect(() => {
    getApiBaseUrl().then(setApiBase)
  }, [])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const buildHistory = useCallback(() => {
    return messages
      .filter((m) => !m.isStreaming)
      .slice(-10) // Keep last 10 messages for context
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
  }, [messages])

  const handleSend = useCallback(
    async (userMessage: string) => {
      if (!schema || !apiBase) return

      const userMsg: ChatMessageType = { id: `user-${Date.now()}`, role: 'user', content: userMessage }
      const assistantMsgId = `assistant-${Date.now()}`
      const assistantMsg: ChatMessageType = { id: assistantMsgId, role: 'assistant', content: '', isStreaming: true }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsLoading(true)

      try {
        const history = buildHistory()
        const sessionToken = (session as any)?.accessToken as string | undefined
        const dataSources = getDataSources(sessionToken)

        const response = await fetch(`${apiBase}/api/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: userMessage, schema, history, data_sources: dataSources }),
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          // detail can be a string or FastAPI's validation array — render either legibly.
          const detail = Array.isArray(errorData.detail)
            ? errorData.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
            : errorData.detail
          throw new Error(detail || `Server error: ${response.status}`)
        }

        const reader = response.body?.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let currentEvent = 'step'

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
            currentEvent = 'step'

            if (eventType === 'step') {
              const step = parsed as WorkflowStep
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsgId) return m
                  const existing = m.liveWorkflowSteps || []
                  const updated = step.status === 'running' || step.status === 'retrying' || step.status === 'fixing'
                    ? [...existing, step]
                    : existing.map((s) =>
                        s.type === step.type && s.alias === step.alias && (s.status === 'running' || s.status === 'retrying' || s.status === 'fixing')
                          ? step : s
                      ).concat(existing.some((s) => s.type === step.type && s.alias === step.alias) ? [] : [step])
                  return { ...m, liveWorkflowSteps: updated }
                })
              )
            } else if (eventType === 'result') {
              const data = parsed
              if (data.type === 'data') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: data.explanation || 'Query executed.', isStreaming: false, liveWorkflowSteps: undefined, queryPlan: data.query_plan || [], queryResults: data.query_results || undefined, planDescription: data.plan_description }
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
                // Schema advice with suggestions
                const suggestions: Suggestion[] = (data.suggestions || []).map((s: Suggestion) => ({
                  ...s,
                  status: 'pending' as const,
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
              const err = parsed.error ?? parsed.message
              throw new Error(typeof err === 'string' ? err : (err ? JSON.stringify(err) : 'Stream error'))
            }
          }
        }

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
              ? { ...m, content: `Failed: ${errorMessage}`, isStreaming: false, liveWorkflowSteps: undefined }
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
      if (!onSchemaChange) return
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
    },
    [schema, onSchemaChange]
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
    },
    []
  )

  const handleSelectClarification = useCallback(
    (_questionId: string, answer: string) => {
      handleSend(answer)
    },
    [handleSend]
  )

  const handleUndo = useCallback(() => {
    if (undoStack.length === 0 || !onSchemaChange) return
    const previousSchema = undoStack[undoStack.length - 1]
    setUndoStack((prev) => prev.slice(0, -1))
    onSchemaChange(previousSchema)
  }, [undoStack, onSchemaChange])

  // Stop events from reaching React Flow's canvas pan/zoom handlers
  const stopPropagation = {
    onPointerDown: (e: React.PointerEvent) => e.stopPropagation(),
    onMouseDown: (e: React.MouseEvent) => e.stopPropagation(),
    onWheel: (e: React.WheelEvent) => e.stopPropagation(),
  }

  return (
    <>
      {/* Floating button */}
      {!isOpen && (
        <button
          onClick={() => { if (!isDragging.current) setIsOpen(true) }}
          onPointerDown={(e) => { e.stopPropagation(); handleDragStart(e) }}
          onMouseDown={(e) => e.stopPropagation()}
          onWheel={(e) => e.stopPropagation()}
          style={{ transform: `translate(${position.x}px, ${position.y}px)` }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 bg-indigo-600 text-white rounded-full shadow-lg shadow-indigo-600/30 hover:bg-indigo-700 transition-shadow cursor-grab active:cursor-grabbing select-none"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
          </svg>
          <span className="text-sm font-medium">Schema Advisor</span>
        </button>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div {...stopPropagation} style={{ transform: `translate(${position.x}px, ${position.y}px)` }} className="fixed bottom-6 right-6 z-50 w-[440px] h-[70vh] max-h-[700px] glass-panel bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl backdrop-blur-xl flex flex-col overflow-hidden animate-fadeIn">
          {/* Header — drag handle */}
          <div
            onPointerDown={handleDragStart}
            className="flex items-center justify-between px-4 py-3 border-b border-slate-700/80 bg-slate-900/80 text-white flex-shrink-0 cursor-grab active:cursor-grabbing select-none">
            <div className="flex items-center gap-2 text-indigo-300">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
              <span className="text-sm font-semibold">Schema Advisor</span>
            </div>
            <div className="flex items-center gap-1">
              {undoStack.length > 0 && (
                <button
                  onClick={handleUndo}
                  className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                  title={`Undo (${undoStack.length})`}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="1 4 1 10 7 10" />
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                  </svg>
                </button>
              )}
              <a
                href="/chat"
                className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                title="Open full chat"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                </svg>
              </a>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-3 chat-scroll">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-12 h-12 rounded-2xl bg-indigo-900/50 border border-indigo-500/30 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(79,70,229,0.3)]">
                  <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
                <h3 className="text-base font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400 mb-1">Schema Advisor</h3>
                <p className="text-xs text-slate-400 mb-5">Understand your data, explore relationships, and ask questions</p>
                <div className="grid grid-cols-2 gap-2 w-full">
                  {[
                    { text: 'What does this database do?', icon: '?' },
                    { text: 'Explain the main data flows', icon: '~' },
                    { text: 'Which tables store customer data?', icon: '#' },
                    { text: 'How are orders connected to payments?', icon: '>' },
                  ].map(({ text, icon }) => (
                    <button
                      key={text}
                      onClick={() => handleSend(text)}
                      disabled={isLoading}
                      className="text-left px-3 py-2.5 text-xs text-slate-300 bg-slate-800/60 border border-slate-700 rounded-xl hover:bg-slate-800 hover:border-indigo-500/50 hover:text-indigo-300 transition-all disabled:opacity-50 group"
                    >
                      <span className="text-indigo-400 font-mono mr-1.5 group-hover:text-indigo-300">{icon}</span>
                      {text}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                onAcceptSuggestion={handleAcceptSuggestion}
                onSkipSuggestion={handleSkipSuggestion}
                onPreviewSuggestion={() => {}}
                onClearPreview={() => {}}
                onSelectClarification={handleSelectClarification}
              />
            ))}
          </div>

          {/* Input */}
          <div className="flex-shrink-0 border-t border-slate-700/80">
            <ChatInput onSend={handleSend} disabled={isLoading} />
          </div>
        </div>
      )}
    </>
  )
}
