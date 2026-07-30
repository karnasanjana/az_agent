'use client'

import { useState, useRef, useEffect } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`
    }
  }, [message])

  const handleSubmit = () => {
    const trimmed = message.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setMessage('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="glass-panel border-t border-slate-700/80 p-3 bg-slate-900/50 backdrop-blur-xl">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || 'Ask about schema optimizations...'}
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none border border-slate-700 bg-slate-900/60 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 disabled:opacity-50 disabled:bg-slate-800 transition-all"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !message.trim()}
          className="px-3 py-2 bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_0_10px_rgba(79,70,229,0.3)] rounded-lg hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
      <p className="text-xs text-slate-500 mt-2">Press Enter to send, Shift+Enter for new line</p>
    </div>
  )
}
