'use client'

import { useState, useEffect } from 'react'
import { listDiagrams, loadDiagram, deleteDiagram, getDiagramSql, shareDiagram, unshareDiagram } from '@/app/actions'
import UserMenu from '@/components/user-menu'
import { ZionLogo } from '@/components/zion-logo'
import type { DiagramMetadata } from '@/types/diagram'

type PageState = 'loading' | 'ready'

export default function SavedDiagramsPage() {
  const [state, setState] = useState<PageState>('loading')
  const [diagrams, setDiagrams] = useState<DiagramMetadata[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const [sqlContent, setSqlContent] = useState<string | null>(null)
  const [sqlDiagramName, setSqlDiagramName] = useState('')
  const [loadingSqlId, setLoadingSqlId] = useState<string | null>(null)
  const [sharingId, setSharingId] = useState<string | null>(null)
  const [copiedShareId, setCopiedShareId] = useState<string | null>(null)

  useEffect(() => {
    async function fetchDiagrams() {
      const result = await listDiagrams()
      setDiagrams(result)
      setState('ready')
    }
    fetchDiagrams()
  }, [])

  const handleOpen = async (id: string) => {
    setLoadingId(id)
    try {
      const result = await loadDiagram(id)
      const diagram = result.diagram as {
        schema?: object
        positions?: Record<string, { x: number; y: number }>
        viewport?: { x: number; y: number; zoom: number }
      }

      if (diagram.schema) {
        sessionStorage.setItem('extracted_schema', JSON.stringify(diagram.schema))
      }
      if (diagram.positions) {
        sessionStorage.setItem('diagram_positions', JSON.stringify(diagram.positions))
      }
      if (diagram.viewport) {
        sessionStorage.setItem('diagram_viewport', JSON.stringify(diagram.viewport))
      }

      // Restore connection configs for auto-reconnect
      const configs = (diagram as any).connection_configs as Array<Record<string, any>> | undefined
      if (configs && Array.isArray(configs)) {
        for (const config of configs) {
          if (config.type === 'sqlserver' && config.host) {
            sessionStorage.setItem('db_credentials', JSON.stringify({
              host: config.host,
              port: config.port || 1433,
              database: config.database,
              username: config.username,
              password: config.password, // Decrypted by backend
            }))
            sessionStorage.setItem('db_type', 'sqlserver')
          }
          if (config.type === 'bigquery' && config.project_id) {
            sessionStorage.setItem('bq_project_id', config.project_id)
          }
          if (config.type === 'dataverse' && config.environment_url) {
            sessionStorage.setItem('dv_environment_url', config.environment_url)
            if (config.access_token) {
              sessionStorage.setItem('dv_access_token', config.access_token)
            }
          }
        }
      }

      // Restore annotations
      const savedAnnotations = (diagram as any).annotations as Array<Record<string, any>> | undefined
      if (savedAnnotations && Array.isArray(savedAnnotations)) {
        sessionStorage.setItem('diagram_annotations', JSON.stringify(savedAnnotations))
      } else {
        sessionStorage.removeItem('diagram_annotations')
      }

      sessionStorage.setItem('current_diagram_id', id)
      const diagramMeta = diagrams.find((d) => d.id === id)
      if (diagramMeta) {
        sessionStorage.setItem('current_diagram_name', diagramMeta.name)
      }

      window.location.href = '/diagram'
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to load diagram')
      setLoadingId(null)
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return
    try {
      await deleteDiagram(id)
      setDiagrams(prev => prev.filter(d => d.id !== id))
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to delete diagram')
    }
  }

  const handleViewSql = async (id: string, name: string) => {
    setLoadingSqlId(id)
    try {
      const sql = await getDiagramSql(id)
      if (sql) {
        setSqlContent(sql)
        setSqlDiagramName(name)
      } else {
        alert('No SQL found for this diagram. Try opening it and saving again.')
      }
    } catch {
      alert('Failed to load SQL')
    } finally {
      setLoadingSqlId(null)
    }
  }

  const handleShare = async (id: string) => {
    setSharingId(id)
    try {
      const diagram = diagrams.find((d) => d.id === id)
      if (diagram?.share_token) {
        // Already shared — copy link
        const url = `${window.location.origin}/shared/${diagram.share_token}`
        await navigator.clipboard.writeText(url)
        setCopiedShareId(id)
        setTimeout(() => setCopiedShareId(null), 2000)
      } else {
        // Generate new share token
        const result = await shareDiagram(id)
        setDiagrams((prev) =>
          prev.map((d) => d.id === id ? { ...d, share_token: result.share_token } : d)
        )
        const url = `${window.location.origin}/shared/${result.share_token}`
        await navigator.clipboard.writeText(url)
        setCopiedShareId(id)
        setTimeout(() => setCopiedShareId(null), 2000)
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to share')
    } finally {
      setSharingId(null)
    }
  }

  const handleUnshare = async (id: string) => {
    try {
      await unshareDiagram(id)
      setDiagrams((prev) =>
        prev.map((d) => d.id === id ? { ...d, share_token: null } : d)
      )
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to unshare')
    }
  }

  const handleCopySql = async () => {
    if (sqlContent) {
      await navigator.clipboard.writeText(sqlContent)
    }
  }

  const handleDownloadSql = () => {
    if (sqlContent) {
      const blob = new Blob([sqlContent], { type: 'text/sql' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sqlDiagramName.replace(/[^a-zA-Z0-9]/g, '_')}_schema.sql`
      a.click()
      URL.revokeObjectURL(url)
    }
  }

  if (state === 'loading') {
    return (
      <main className="min-h-screen bg-gradient-surface flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-indigo-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-500 text-sm">Loading diagrams...</p>
        </div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gradient-surface flex flex-col">
      {/* Header */}
      <header className="glass-panel border-b border-white/10 text-white flex-shrink-0 relative z-30">
        <div className="px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <ZionLogo className="h-8 text-white drop-shadow-[0_0_15px_rgba(79,70,229,0.4)]" />
              <div className="h-6 w-px bg-slate-700/80 mx-2"></div>
              <span className="text-xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-slate-100 to-slate-300">
                Command Center
              </span>
            </a>
          </div>
          <UserMenu />
        </div>
      </header>

      {/* Content */}
      <div className="px-8 py-8">
        {/* Page header with search */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400 tracking-tight drop-shadow-sm">My Diagrams</h1>
            <p className="text-sm text-slate-400 mt-1.5 font-medium">
              {diagrams.length} saved diagram{diagrams.length !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {diagrams.length > 0 && (
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search diagrams..."
                  className="w-64 pl-9 pr-8 py-2.5 text-sm bg-slate-900/60 backdrop-blur-md border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 text-slate-200 placeholder:text-slate-500 transition-all shadow-sm"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                )}
              </div>
            )}
            <a
              href="/"
              className="px-4 py-2.5 text-sm bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 border border-indigo-500/50 shadow-[0_0_15px_rgba(79,70,229,0.4)] transition-all font-medium whitespace-nowrap"
            >
              New Diagram
            </a>
          </div>
        </div>

        {/* Empty state */}
        {diagrams.length === 0 && (
          <div className="glass-panel bg-slate-900/40 rounded-3xl border border-slate-700/80 p-16 text-center">
            <div className="mx-auto w-16 h-16 rounded-2xl bg-indigo-900/50 flex items-center justify-center mb-6 border border-indigo-500/30">
              <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-slate-200 mb-2">No saved diagrams yet</h2>
            <p className="text-slate-400 mb-8 max-w-sm mx-auto">
              Connect to a database, extract the schema, and save your first diagram.
            </p>
            <a
              href="/"
              className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors font-medium shadow-sm"
            >
              Connect to Database
            </a>
          </div>
        )}

        {/* Diagram cards grid */}
        {diagrams.length > 0 && (() => {
          const query = searchQuery.toLowerCase().trim()
          const filtered = query
            ? diagrams.filter((d) =>
                d.name.toLowerCase().includes(query) ||
                (d.database_name || '').toLowerCase().includes(query)
              )
            : diagrams

          if (filtered.length === 0 && query) {
            return (
              <div className="text-center py-12">
                <p className="text-slate-400 text-sm">No diagrams matching &ldquo;{searchQuery}&rdquo;</p>
              </div>
            )
          }

          return (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {filtered.map((diagram) => (
              <div
                key={diagram.id}
                className="glass-panel bg-slate-900/60 border border-slate-700/80 rounded-2xl p-5 hover:shadow-[0_0_25px_rgba(99,102,241,0.2)] hover:border-indigo-500/50 hover:-translate-y-1 transition-all duration-300 group"
              >
                {/* Card header */}
                <div className="mb-4">
                  <h3 className="text-lg font-semibold text-slate-200 mb-0.5 truncate group-hover:text-indigo-400 transition-colors">
                    {diagram.name}
                  </h3>
                  {diagram.database_name && (
                    <p className="text-xs text-slate-400 truncate">{diagram.database_name}</p>
                  )}
                </div>

                {/* Metadata */}
                <div className="flex items-center gap-3 text-xs text-slate-400 mb-4">
                  <span className="flex items-center gap-1">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-300">
                      <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
                    </svg>
                    {diagram.table_count} tables
                  </span>
                  <span>
                    {new Date(diagram.updated_at).toLocaleDateString('en-US', {
                      month: 'short', day: 'numeric', year: 'numeric',
                    })}
                  </span>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleOpen(diagram.id)}
                    disabled={loadingId === diagram.id}
                    className="px-4 py-2 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)] transition-all disabled:opacity-50 font-medium"
                  >
                    {loadingId === diagram.id ? 'Loading...' : 'Open'}
                  </button>
                  <button
                    onClick={() => handleViewSql(diagram.id, diagram.name)}
                    disabled={loadingSqlId === diagram.id}
                    className="px-3 py-2 text-sm text-slate-400 hover:text-indigo-300 hover:bg-indigo-900/30 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {loadingSqlId === diagram.id ? '...' : 'View SQL'}
                  </button>
                  <button
                    onClick={() => handleShare(diagram.id)}
                    disabled={sharingId === diagram.id}
                    className="px-3 py-2 text-sm text-slate-400 hover:text-emerald-300 hover:bg-emerald-900/20 rounded-lg transition-colors disabled:opacity-50"
                    title={diagram.share_token ? 'Copy share link' : 'Share diagram'}
                  >
                    {copiedShareId === diagram.id ? 'Copied!' : sharingId === diagram.id ? '...' : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
                        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                      </svg>
                    )}
                  </button>
                  {diagram.share_token && (
                    <button
                      onClick={() => handleUnshare(diagram.id)}
                      className="px-2 py-2 text-sm text-slate-500 hover:text-amber-400 hover:bg-amber-900/20 rounded-lg transition-colors"
                      title="Revoke share link"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M18.36 6.64a9 9 0 11-12.73 0" /><line x1="12" y1="2" x2="12" y2="12" />
                      </svg>
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(diagram.id, diagram.name)}
                    className="px-3 py-2 text-sm text-slate-500 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors ml-auto"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
          )
        })()}
      </div>

      {/* SQL Viewer Modal */}
      {sqlContent && (
        <>
          <div className="fixed inset-0 bg-black/70 z-50 backdrop-blur-md" onClick={() => setSqlContent(null)} />
          <div className="fixed inset-4 z-50 flex items-center justify-center">
            <div className="glass-panel bg-slate-900/95 rounded-2xl shadow-2xl w-full max-w-4xl h-full max-h-[90vh] flex flex-col border border-slate-700">
              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-900/50">
                <div>
                  <h2 className="text-lg font-bold text-slate-200">Schema DDL</h2>
                  <p className="text-xs text-slate-400 mt-1">{sqlDiagramName}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCopySql}
                    className="px-3 py-1.5 text-sm border border-slate-700 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 hover:text-white transition-colors"
                  >
                    Copy
                  </button>
                  <button
                    onClick={handleDownloadSql}
                    className="px-3 py-1.5 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 shadow-sm transition-colors"
                  >
                    Download .sql
                  </button>
                  <button
                    onClick={() => setSqlContent(null)}
                    className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="flex-1 overflow-auto bg-[#0d1117] rounded-b-2xl">
                <pre className="p-5 text-sm font-mono text-slate-300 leading-relaxed whitespace-pre">{sqlContent}</pre>
              </div>
            </div>
          </div>
        </>
      )}
    </main>
  )
}
