'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { DiagramCanvas } from '@/components/diagram/diagram-canvas'
import { ZionLogo } from '@/components/zion-logo'
import { schemaToNodes, schemaToEdges, getDatasetColor } from '@/lib/diagram-utils'
import { getLayoutedNodes } from '@/lib/layout'
import { SharedRelationshipsPanel } from '@/components/diagram/shared-relationships-panel'
import { loadSharedDiagram } from '@/app/actions'
import type { DatabaseSchema } from '@/types/schema'
import type { TableNodeData, RelationshipEdgeData } from '@/types/diagram'
import type { Node, Edge } from '@xyflow/react'

type PageState = 'loading' | 'error' | 'ready'

interface ShareSettings {
  show_relationships?: boolean
  share_note?: string
}

export default function SharedDiagramPage() {
  const params = useParams()
  const token = params.token as string

  const [state, setState] = useState<PageState>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [diagramName, setDiagramName] = useState('')
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [nodes, setNodes] = useState<Node<TableNodeData>[]>([])
  const [edges, setEdges] = useState<Edge<RelationshipEdgeData>[]>([])
  const [shareNote, setShareNote] = useState('')
  const [showRelationships, setShowRelationships] = useState(false)

  useEffect(() => {
    async function loadShared() {
      try {
        const data = await loadSharedDiagram(token as string)
        const diagramData = data.diagram as Record<string, unknown>
        const parsedSchema = diagramData.schema as DatabaseSchema
        const positions = diagramData.positions as Record<string, { x: number; y: number }> | undefined
        const settings = ((data.metadata as unknown as Record<string, unknown>).share_settings || {}) as ShareSettings

        setDiagramName(data.metadata.name)
        setSchema(parsedSchema)
        setShareNote(settings.share_note || '')

        // Build nodes and edges
        const datasetNames = Array.from(new Set(parsedSchema.tables.map((t) => t.schema_name)))
        const datasetColors: Record<string, string> = Object.fromEntries(
          datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
        )

        let createdNodes = schemaToNodes(parsedSchema.tables, parsedSchema.foreign_keys, datasetColors)
        const createdEdges = schemaToEdges(parsedSchema.foreign_keys, parsedSchema.tables)

        // Apply saved positions or auto-layout
        if (positions && Object.keys(positions).length > 0) {
          createdNodes = createdNodes.map((node) => ({
            ...node,
            position: positions[node.id] || node.position,
          }))
        } else {
          createdNodes = getLayoutedNodes(createdNodes, createdEdges, 'TB')
        }

        setNodes(createdNodes)
        // Only show edges if sharer enabled relationships
        setEdges(settings.show_relationships ? createdEdges : [])
        setState('ready')
      } catch (err) {
        setErrorMsg('Failed to load shared diagram. Please check the link.')
        setState('error')
      }
    }

    if (token) loadShared()
  }, [token])

  if (state === 'loading') {
    return (
      <main className="min-h-screen bg-gradient-surface flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-indigo-500 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-500 text-sm">Loading shared diagram...</p>
        </div>
      </main>
    )
  }

  if (state === 'error') {
    return (
      <main className="min-h-screen bg-gradient-surface flex items-center justify-center p-4">
        <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-10 text-center max-w-md">
          <div className="mx-auto w-14 h-14 rounded-2xl bg-red-900/50 flex items-center justify-center mb-5 border border-red-500/30">
            <svg className="w-7 h-7 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-slate-200 mb-2">Link Not Found</h1>
          <p className="text-slate-400 text-sm mb-6">{errorMsg}</p>
          <a href="/" className="inline-block px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 transition-colors font-medium text-sm">
            Go to SchemaViz
          </a>
        </div>
      </main>
    )
  }

  return (
    <main className="h-screen flex flex-col">
      {/* Header - read-only */}
      <header className="glass-panel px-4 py-2.5 flex items-center justify-between flex-shrink-0 relative z-30 border-b border-white/10">
        <div className="flex items-center gap-4">
          <div className="border-r border-slate-700/80 pr-4">
            <a href="/">
              <ZionLogo className="h-7 text-white drop-shadow-[0_0_15px_rgba(79,70,229,0.4)]" />
            </a>
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide">{diagramName}</h1>
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-xs text-white/60">
                {schema?.table_count} tables{edges.length > 0 ? `, ${edges.length} relationships` : ''}
              </p>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                Read-only
              </span>
            </div>
          </div>
        </div>
        <a
          href="/"
          className="px-4 py-1.5 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 transition-all shadow-[0_0_10px_rgba(79,70,229,0.5)] font-medium"
        >
          Try SchemaViz
        </a>
      </header>

      {/* Share note banner */}
      {shareNote && (
        <div className="bg-indigo-950/40 border-b border-indigo-500/20 px-4 py-3 flex items-start gap-3">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-400 flex-shrink-0 mt-0.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <p className="text-sm text-indigo-200/80">{shareNote}</p>
        </div>
      )}

      {/* Canvas */}
      <div className="flex-1 relative">
        <DiagramCanvas
          initialNodes={nodes}
          initialEdges={edges}
          highlightedNodes={null}
        />

        {/* Floating Relationships button */}
        {schema && schema.foreign_keys.length > 0 && (
          <button
            onClick={() => setShowRelationships(true)}
            className="absolute bottom-6 right-6 flex items-center gap-2 px-4 py-2.5 bg-slate-900/90 border border-slate-700 rounded-xl text-sm text-slate-300 hover:bg-slate-800 hover:text-slate-100 hover:border-slate-600 transition-all shadow-xl backdrop-blur-sm z-10"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
            Relationships ({schema.foreign_keys.length})
          </button>
        )}
      </div>

      {/* Relationships panel */}
      <SharedRelationshipsPanel
        isOpen={showRelationships}
        onClose={() => setShowRelationships(false)}
        foreignKeys={schema?.foreign_keys ?? []}
      />
    </main>
  )
}
