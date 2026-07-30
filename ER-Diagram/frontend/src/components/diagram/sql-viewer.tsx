'use client'

import { useState } from 'react'

interface SqlViewerProps {
  isOpen: boolean
  onClose: () => void
  sql: string
  databaseName: string
}

export function SqlViewer({ isOpen, onClose, sql, databaseName }: SqlViewerProps) {
  const [copied, setCopied] = useState(false)

  if (!isOpen) return null

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([sql], { type: 'text/sql' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${databaseName.replace(/[^a-zA-Z0-9]/g, '_')}_schema.sql`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/70 backdrop-blur-md z-50" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-4 z-50 flex items-center justify-center">
        <div className="glass-panel bg-slate-900/95 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-4xl h-full max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/80 bg-slate-900/50">
            <div>
              <h2 className="text-lg font-bold text-slate-200">Schema DDL</h2>
              <p className="text-xs text-slate-400 mt-1">{databaseName}</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors flex items-center gap-1.5 ${
                  copied
                    ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-500/30'
                    : 'border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
                }`}
              >
                {copied ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Copied
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                    Copy
                  </>
                )}
              </button>
              <button
                onClick={handleDownload}
                className="px-3 py-1.5 text-sm border border-indigo-500/50 text-white bg-indigo-600 rounded-lg hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)] transition-colors flex items-center gap-1.5"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download .sql
              </button>
              <button
                onClick={onClose}
                className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          {/* SQL content */}
          <div className="flex-1 overflow-auto bg-[#0d1117] rounded-b-2xl">
            <pre className="p-5 text-sm font-mono text-slate-300 leading-relaxed whitespace-pre">{sql}</pre>
          </div>
        </div>
      </div>
    </>
  )
}
