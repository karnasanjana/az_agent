'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { DiagramCanvas } from '@/components/diagram/diagram-canvas'
import { Toolbar } from '@/components/diagram/toolbar'
import { SaveDialog } from '@/components/diagram/save-dialog'
import { SqlViewer } from '@/components/diagram/sql-viewer'
import { RelationshipsPanel } from '@/components/diagram/relationships-panel'
import { InferRelationshipsPanel } from '@/components/diagram/infer-relationships-panel'
import { AddDataSourceModal } from '@/components/diagram/add-data-source-modal'
import { SchemaPreviewToggle } from '@/components/diagram/schema-preview-toggle'
import { ShareDialog } from '@/components/diagram/share-dialog'
import { AnnotationsPanel } from '@/components/diagram/annotations-panel'
import { ImpactAnalysisPanel } from '@/components/diagram/impact-analysis-panel'
import { SchemaHistoryPanel } from '@/components/diagram/schema-history-panel'
import { LineagePanel } from '@/components/diagram/lineage-panel'
import { HiddenTablesPanel } from '@/components/diagram/hidden-tables-panel'
import { cloneSchema } from '@/lib/schema-diff'
import UserMenu from '@/components/user-menu'
import { ZionLogo } from '@/components/zion-logo'
import { schemaToNodes, schemaToEdges, manualRelationshipsToEdges, getDatasetColor, detectCrossDatasetRelationships } from '@/lib/diagram-utils'
import { getLayoutedNodes } from '@/lib/layout'
import { exportDiagramAsPdf } from '@/lib/export-pdf'
import { generateDDL } from '@/lib/generate-sql'
import { saveDiagram, saveDiagramSql, updateDiagram, shareDiagram, unshareDiagram, updateShareSettings, autoDocumentSchema } from '@/app/actions'
import FloatingChat from '@/components/chat/floating-chat'
import type { DatabaseSchema, ForeignKey } from '@/types/schema'
import type { TableNodeData, RelationshipEdgeData, ManualRelationship, SuggestedRelationship, Annotation } from '@/types/diagram'
import type { Node, Edge } from '@xyflow/react'

type PageState = 'loading' | 'empty' | 'ready'

export default function DiagramPage() {
  const [state, setState] = useState<PageState>('loading')
  const [nodes, setNodes] = useState<Node<TableNodeData>[]>([])
  const [edges, setEdges] = useState<Edge<RelationshipEdgeData>[]>([])
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)

  // Manual relationships state
  const [manualRelationships, setManualRelationships] = useState<ManualRelationship[]>([])

  // Multi-dataset state
  const [loadedDatasets, setLoadedDatasets] = useState<string[]>([])
  const [showAddDataset, setShowAddDataset] = useState(false)
  const [crossDatasetBanner, setCrossDatasetBanner] = useState<SuggestedRelationship[] | null>(null)

  // Hover state for edge highlighting (temporary, clears on mouse leave)
  const [hoveredEdge, setHoveredEdge] = useState<{
    sourceId: string
    targetId: string
  } | null>(null)

  // Selected edge state (sticky, clears on pane click)
  const [selectedEdge, setSelectedEdge] = useState<{
    sourceId: string
    targetId: string
  } | null>(null)

  // Auto layout trigger
  const [layoutTrigger, setLayoutTrigger] = useState(0)

  // Export PDF state
  const [isExporting, setIsExporting] = useState(false)

  // Relationships panel state
  const [showRelationships, setShowRelationships] = useState(false)

  // AI infer relationships panel state
  const [showInferRelationships, setShowInferRelationships] = useState(false)

  // Save dialog state
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // Current diagram tracking (for save vs save-as)
  const [currentDiagramId, setCurrentDiagramId] = useState<string | null>(null)
  const [currentDiagramName, setCurrentDiagramName] = useState<string | null>(null)

  // SQL viewer state
  const [showSqlViewer, setShowSqlViewer] = useState(false)

  // Share dialog state
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [shareToken, setShareToken] = useState<string | null>(null)
  const [shareSettings, setShareSettings] = useState<{ showRelationships: boolean; shareNote: string }>({ showRelationships: false, shareNote: '' })

  // Annotations state
  const [showAnnotations, setShowAnnotations] = useState(false)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [hiddenTables, setHiddenTables] = useState<Set<string>>(new Set())

  // Impact analysis state
  const [showImpactAnalysis, setShowImpactAnalysis] = useState(false)

  // Schema change history state
  const [showHistory, setShowHistory] = useState(false)

  // Lineage panel state
  const [showLineage, setShowLineage] = useState(false)

  // AI Schema Advisor highlight state (used when returning from /chat)
  const [advisorHighlightedTables] = useState<Set<string> | null>(null)

  // Preview mode state (Before/After toggle)
  const [previewMode, setPreviewMode] = useState(false)
  const [previewView, setPreviewView] = useState<'before' | 'after'>('after')
  const [previewSchema, setPreviewSchema] = useState<DatabaseSchema | null>(null)
  const [previewNodes, setPreviewNodes] = useState<Node<TableNodeData>[]>([])
  const [previewEdges, setPreviewEdges] = useState<Edge<RelationshipEdgeData>[]>([])
  const [previewAppliedCount, setPreviewAppliedCount] = useState(0)
  const [previewTotalCount, setPreviewTotalCount] = useState(0)

  // Track current node positions from DiagramCanvas
  const currentNodesRef = useRef<Node<TableNodeData>[]>([])

  const handleNodesUpdate = useCallback((updatedNodes: Node<TableNodeData>[]) => {
    currentNodesRef.current = updatedNodes
  }, [])

  const handleAutoLayout = useCallback(() => {
    setLayoutTrigger(prev => prev + 1)
  }, [])

  // Hide/restore table handlers
  const handleHideTable = useCallback((tableId: string) => {
    setHiddenTables(prev => {
      const next = new Set(prev)
      next.add(tableId)
      return next
    })
    // Remove the node and its connected edges
    setNodes(prev => prev.filter(n => n.id !== tableId))
    setEdges(prev => prev.filter(e => e.source !== tableId && e.target !== tableId))
  }, [])

  const handleRestoreTable = useCallback((tableId: string) => {
    setHiddenTables(prev => {
      const next = new Set(prev)
      next.delete(tableId)
      return next
    })
  }, [])

  const handleRestoreAllTables = useCallback(() => {
    setHiddenTables(new Set())
  }, [])

  // Rebuild nodes/edges when hiddenTables changes (restore flow)
  useEffect(() => {
    if (!schema || state !== 'ready') return
    const { nodes: newNodes, edges: newEdges } = buildNodesAndEdges(schema)
    setNodes(newNodes)
    setEdges(newEdges)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hiddenTables])

  // Auto-document state
  const [isAutoDocumenting, setIsAutoDocumenting] = useState(false)

  const handleAutoDocument = useCallback(async () => {
    if (!schema || isAutoDocumenting) return
    setIsAutoDocumenting(true)
    try {
      const payload = await autoDocumentSchema(schema)
      if (payload.error) throw new Error(payload.error)
      const returnedSchema = payload?.schema as DatabaseSchema | undefined
      if (!returnedSchema) throw new Error('Auto-document response missing schema')

      // Merge descriptions into current schema (preserve any other state)
      const merged: DatabaseSchema = {
        ...schema,
        tables: schema.tables.map((t) => {
          const updated = returnedSchema.tables.find(
            (rt) => rt.table_name === t.table_name && rt.schema_name === t.schema_name
          )
          if (!updated) return t
          return {
            ...t,
            description: updated.description ?? t.description,
            columns: t.columns.map((c) => {
              const uc = updated.columns.find((x) => x.name === c.name)
              return uc ? { ...c, description: uc.description ?? c.description } : c
            }),
          }
        }),
      }

      setSchema(merged)
      sessionStorage.setItem('extracted_schema', JSON.stringify(merged))

      // Refresh nodes so the new descriptions show up immediately
      setNodes((prev) =>
        prev.map((node) => {
          const t = merged.tables.find(
            (mt) => mt.table_name === node.data.table_name && mt.schema_name === node.data.schema_name
          )
          if (!t) return node
          return {
            ...node,
            data: {
              ...node.data,
              description: t.description,
              columns: t.columns,
            },
          }
        })
      )
    } catch (err) {
      console.error('Auto-document failed:', err)
      window.alert(`Auto-document failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsAutoDocumenting(false)
    }
  }, [schema, isAutoDocumenting])

  // Manual relationship handlers
  const handleAddManualRelationship = useCallback((relationship: ManualRelationship) => {
    setManualRelationships((prev) => {
      const updated = [...prev, relationship]
      sessionStorage.setItem('manual_relationships', JSON.stringify(updated))
      return updated
    })
  }, [])

  const handleDeleteManualRelationship = useCallback((edgeId: string) => {
    setManualRelationships((prev) => {
      const updated = prev.filter((r) => r.id !== edgeId)
      sessionStorage.setItem('manual_relationships', JSON.stringify(updated))
      return updated
    })
  }, [])

  // Accept an AI-inferred foreign key and add it to the schema
  const handleAcceptInferredRelationship = useCallback((fk: ForeignKey) => {
    setSchema((prev) => {
      if (!prev) return prev
      // Avoid exact duplicate constraint name
      if (prev.foreign_keys.some((existing) => existing.constraint_name === fk.constraint_name)) {
        return prev
      }
      const updated: DatabaseSchema = {
        ...prev,
        foreign_keys: [...prev.foreign_keys, fk],
      }
      sessionStorage.setItem('extracted_schema', JSON.stringify(updated))

      // Rebuild nodes and edges
      const datasetNames = Array.from(new Set(updated.tables.map((t) => t.schema_name)))
      const datasetColors: Record<string, string> = Object.fromEntries(
        datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
      )
      let newNodes = schemaToNodes(updated.tables, updated.foreign_keys, datasetColors)
      const newEdges = schemaToEdges(updated.foreign_keys, updated.tables)
      // Preserve current positions where possible
      const currentPositions = new Map<string, { x: number; y: number }>()
      for (const node of currentNodesRef.current) {
        currentPositions.set(node.id, node.position)
      }
      newNodes = newNodes.map((n) => ({
        ...n,
        position: currentPositions.get(n.id) || n.position,
      }))
      setNodes(newNodes)
      setEdges(newEdges)

      return updated
    })
  }, [])

  // Delete an auto-detected relationship (FK)
  const handleDeleteAutoRelationship = useCallback((constraintName: string) => {
    setSchema((prev) => {
      if (!prev) return prev
      const updated: DatabaseSchema = {
        ...prev,
        foreign_keys: prev.foreign_keys.filter((fk) => fk.constraint_name !== constraintName),
      }
      sessionStorage.setItem('extracted_schema', JSON.stringify(updated))

      // Rebuild nodes and edges
      const datasetNames = Array.from(new Set(updated.tables.map((t) => t.schema_name)))
      const datasetColors: Record<string, string> = Object.fromEntries(
        datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
      )
      let newNodes = schemaToNodes(updated.tables, updated.foreign_keys, datasetColors)
      const newEdges = schemaToEdges(updated.foreign_keys, updated.tables)
      newNodes = getLayoutedNodes(newNodes, newEdges, 'TB')
      setNodes(newNodes)
      setEdges(newEdges)

      return updated
    })
  }, [])

  // Remove a dataset and all its tables, FKs, and manual relationships
  const handleRemoveDataset = useCallback((datasetName: string) => {
    setSchema((prev) => {
      if (!prev) return prev

      // Remove tables from this dataset
      const remainingTables = prev.tables.filter((t) => t.schema_name !== datasetName)
      if (remainingTables.length === 0) {
        // Last dataset — go back to home
        sessionStorage.removeItem('extracted_schema')
        sessionStorage.removeItem('manual_relationships')
        window.location.href = '/'
        return prev
      }

      // Remove FKs where source or target is in this dataset
      const remainingFks = prev.foreign_keys.filter(
        (fk) => fk.source_schema !== datasetName && fk.target_schema !== datasetName
      )

      // Remove dataset from order and source tracking
      const updatedOrder = { ...(prev.dataset_order || {}) }
      delete updatedOrder[datasetName]
      const updatedSources: Record<string, 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'> = { ...(prev.dataset_sources || {}) }
      delete updatedSources[datasetName]

      const updated: DatabaseSchema = {
        ...prev,
        tables: remainingTables,
        foreign_keys: remainingFks,
        table_count: remainingTables.length,
        dataset_order: updatedOrder,
        dataset_sources: updatedSources,
      }
      sessionStorage.setItem('extracted_schema', JSON.stringify(updated))

      // Remove manual relationships involving this dataset
      setManualRelationships((prevRels) => {
        const filtered = prevRels.filter(
          (r) => r.source_database !== datasetName && r.target_database !== datasetName
        )
        sessionStorage.setItem('manual_relationships', JSON.stringify(filtered))
        return filtered
      })

      // Rebuild nodes and edges
      const datasetNames = Array.from(new Set(remainingTables.map((t) => t.schema_name)))
      setLoadedDatasets(datasetNames)

      const datasetColors: Record<string, string> = Object.fromEntries(
        datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
      )
      let newNodes = schemaToNodes(remainingTables, remainingFks, datasetColors)
      const newEdges = schemaToEdges(remainingFks, remainingTables)
      newNodes = getLayoutedNodes(newNodes, newEdges, 'TB')
      setNodes(newNodes)
      setEdges(newEdges)

      return updated
    })
  }, [])

  // Convert manual relationships to React Flow edges
  const manualEdges = useMemo(
    () => manualRelationshipsToEdges(manualRelationships),
    [manualRelationships]
  )

  const handleExportPdf = useCallback(async () => {
    setIsExporting(true)
    try {
      await exportDiagramAsPdf(
        () => currentNodesRef.current,
        {
          databaseName: schema?.database_name || 'Database',
          tableCount: schema?.table_count || 0,
          relationshipCount: schema?.foreign_keys.length || 0,
          foreignKeys: schema?.foreign_keys || [],
        },
        edges
      )
    } catch (error) {
      console.error('PDF export failed:', error)
      alert('Failed to generate PDF. Please try again.')
    } finally {
      setIsExporting(false)
    }
  }, [schema])

  // Handle adding a new dataset to the diagram
  const handleAddDataset = useCallback((newSchema: DatabaseSchema, sourceType?: 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse') => {
    setSchema((prevSchema) => {
      if (!prevSchema) {
        // First dataset — assign order 1 to all its schema_names
        const datasetNames = Array.from(new Set(newSchema.tables.map((t) => t.schema_name)))
        const order: Record<string, number> = {}
        const sources: Record<string, 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'> = {}
        datasetNames.forEach((ds, i) => {
          order[ds] = i + 1
          if (sourceType) sources[ds] = sourceType
        })
        return { ...newSchema, dataset_order: order, dataset_sources: sources }
      }

      const existingTableIds = new Set(
        prevSchema.tables.map((t) => `${t.schema_name}.${t.table_name}`)
      )
      const newTables = newSchema.tables.filter(
        (t) => !existingTableIds.has(`${t.schema_name}.${t.table_name}`)
      )
      const mergedTables = [...prevSchema.tables, ...newTables]

      const existingFkNames = new Set(prevSchema.foreign_keys.map((fk) => fk.constraint_name))
      const newFks = newSchema.foreign_keys.filter(
        (fk) => !existingFkNames.has(fk.constraint_name)
      )
      const mergedFks = [...prevSchema.foreign_keys, ...newFks]

      // Track dataset addition order
      const prevOrder = prevSchema.dataset_order || {}
      const maxOrder = Object.values(prevOrder).length > 0
        ? Math.max(...Object.values(prevOrder))
        : 0
      const newDatasetNames = Array.from(new Set(newTables.map((t) => t.schema_name)))
        .filter((ds) => !(ds in prevOrder))
      const updatedOrder = { ...prevOrder }
      newDatasetNames.forEach((ds, i) => { updatedOrder[ds] = maxOrder + i + 1 })

      // Track source type per dataset
      const updatedSources: Record<string, 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'> = { ...(prevSchema.dataset_sources || {}) }
      if (sourceType) {
        newDatasetNames.forEach((ds) => { updatedSources[ds] = sourceType })
      }

      const merged: DatabaseSchema = {
        ...prevSchema,
        tables: mergedTables,
        foreign_keys: mergedFks,
        table_count: mergedTables.length,
        dataset_order: updatedOrder,
        dataset_sources: updatedSources,
      }

      sessionStorage.setItem('extracted_schema', JSON.stringify(merged))

      const allDatasetNames = Array.from(
        new Set(mergedTables.map((t) => t.schema_name))
      )

      const datasetColors: Record<string, string> = {}
      for (const ds of allDatasetNames) {
        datasetColors[ds] = getDatasetColor(ds, allDatasetNames)
      }

      let newNodes = schemaToNodes(mergedTables, mergedFks, datasetColors)
      const newEdges = schemaToEdges(mergedFks, mergedTables)

      newNodes = getLayoutedNodes(newNodes, newEdges, 'TB')

      setNodes(newNodes)
      setEdges(newEdges)
      setLoadedDatasets(allDatasetNames)

      if (allDatasetNames.length > 1) {
        const suggestions = detectCrossDatasetRelationships(mergedTables)
        if (suggestions.length > 0) {
          setCrossDatasetBanner(suggestions)
        }
      }

      return merged
    })
  }, [])

  const handleAcceptSuggestions = useCallback(() => {
    if (!crossDatasetBanner) return

    for (const suggestion of crossDatasetBanner) {
      const relationship: ManualRelationship = {
        id: `suggested_${suggestion.sourceDataset}.${suggestion.sourceTable}.${suggestion.sourceColumn}_${suggestion.targetDataset}.${suggestion.targetTable}.${suggestion.targetColumn}_${Date.now()}`,
        source_database: suggestion.sourceDataset,
        source_table: suggestion.sourceTable,
        source_column: suggestion.sourceColumn,
        target_database: suggestion.targetDataset,
        target_table: suggestion.targetTable,
        target_column: suggestion.targetColumn,
      }
      handleAddManualRelationship(relationship)
    }

    setCrossDatasetBanner(null)
  }, [crossDatasetBanner, handleAddManualRelationship])

  // Helper to build nodes/edges from a schema (filters out hidden tables)
  const buildNodesAndEdges = useCallback((s: DatabaseSchema) => {
    const datasetNames = Array.from(new Set(s.tables.map((t) => t.schema_name)))
    const datasetColors: Record<string, string> = Object.fromEntries(
      datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
    )
    // Filter out hidden tables
    const visibleTables = s.tables.filter(t => !hiddenTables.has(`${t.schema_name}.${t.table_name}`))
    const visibleFks = s.foreign_keys.filter(fk => {
      const srcId = `${fk.source_schema}.${fk.source_table}`
      const tgtId = `${fk.target_schema}.${fk.target_table}`
      return !hiddenTables.has(srcId) && !hiddenTables.has(tgtId)
    })
    let newNodes = schemaToNodes(visibleTables, visibleFks, datasetColors)
    const newEdges = schemaToEdges(visibleFks, visibleTables)
    // Inject onHideTable callback into every node
    newNodes = newNodes.map(n => ({ ...n, data: { ...n.data, onHideTable: handleHideTable } }))
    newNodes = getLayoutedNodes(newNodes, newEdges, 'TB')
    return { nodes: newNodes, edges: newEdges, datasetNames }
  }, [hiddenTables, handleHideTable])

  // Enter preview mode when suggestions arrive
  const handleEnterPreview = useCallback((totalSuggestions: number) => {
    if (!schema) return
    setPreviewMode(true)
    setPreviewView('after')
    setPreviewSchema(cloneSchema(schema))
    const { nodes: pNodes, edges: pEdges } = buildNodesAndEdges(schema)
    setPreviewNodes(pNodes)
    setPreviewEdges(pEdges)
    setPreviewAppliedCount(0)
    setPreviewTotalCount(totalSuggestions)
  }, [schema, buildNodesAndEdges])

  // Handle schema changes from the AI advisor (preview-aware)
  const handleSchemaChange = useCallback((newSchema: DatabaseSchema) => {
    if (previewMode) {
      // Update the preview schema (After view)
      setPreviewSchema(newSchema)
      const { nodes: pNodes, edges: pEdges } = buildNodesAndEdges(newSchema)
      setPreviewNodes(pNodes)
      setPreviewEdges(pEdges)
      setPreviewAppliedCount((prev) => prev + 1)
    } else {
      // Direct apply (no preview mode)
      setSchema(newSchema)
      sessionStorage.setItem('extracted_schema', JSON.stringify(newSchema))
      const { nodes: newNodes, edges: newEdges, datasetNames } = buildNodesAndEdges(newSchema)
      setLoadedDatasets(datasetNames)
      setNodes(newNodes)
      setEdges(newEdges)
    }
  }, [previewMode, buildNodesAndEdges])

  // Confirm preview changes — apply "After" schema as the new current
  const handleConfirmPreview = useCallback(() => {
    if (!previewSchema) return
    setSchema(previewSchema)
    sessionStorage.setItem('extracted_schema', JSON.stringify(previewSchema))
    const { nodes: newNodes, edges: newEdges, datasetNames } = buildNodesAndEdges(previewSchema)
    setLoadedDatasets(datasetNames)
    setNodes(newNodes)
    setEdges(newEdges)
    // Exit preview mode
    setPreviewMode(false)
    setPreviewSchema(null)
    setPreviewNodes([])
    setPreviewEdges([])
  }, [previewSchema, buildNodesAndEdges])

  // Discard preview changes — go back to original
  const handleDiscardPreview = useCallback(() => {
    setPreviewMode(false)
    setPreviewSchema(null)
    setPreviewNodes([])
    setPreviewEdges([])
    setPreviewAppliedCount(0)
    setPreviewTotalCount(0)
  }, [])

  // Load schema from sessionStorage on mount
  useEffect(() => {
    const stored = sessionStorage.getItem('extracted_schema')

    if (!stored) {
      setState('empty')
      return
    }

    try {
      const parsedSchema: DatabaseSchema = JSON.parse(stored)

      if (!parsedSchema.tables || parsedSchema.tables.length === 0) {
        setState('empty')
        return
      }

      // Ensure dataset_order exists (for schemas saved before this feature)
      if (!parsedSchema.dataset_order) {
        const dsNames = Array.from(new Set(parsedSchema.tables.map((t) => t.schema_name)))
        parsedSchema.dataset_order = {}
        dsNames.forEach((ds, i) => { parsedSchema.dataset_order![ds] = i + 1 })
      }

      // Ensure dataset_sources exists (for schemas saved before this feature)
      // Try to infer from sessionStorage db_type, otherwise leave empty
      if (!parsedSchema.dataset_sources) {
        const dbType = sessionStorage.getItem('db_type')
        if (dbType) {
          const dsNames = Array.from(new Set(parsedSchema.tables.map((t) => t.schema_name)))
          parsedSchema.dataset_sources = {}
          dsNames.forEach((ds) => {
            parsedSchema.dataset_sources![ds] = dbType as 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'
          })
        }
      }

      setSchema(parsedSchema)

      const datasetNames = Array.from(
        new Set(parsedSchema.tables.map((t) => t.schema_name))
      )
      setLoadedDatasets(datasetNames)

      const datasetColors: Record<string, string> = Object.fromEntries(
        datasetNames.map((ds) => [ds, getDatasetColor(ds, datasetNames)])
      )

      let createdNodes = schemaToNodes(parsedSchema.tables, parsedSchema.foreign_keys, datasetColors)
      const createdEdges = schemaToEdges(parsedSchema.foreign_keys, parsedSchema.tables)

      const savedPositions = sessionStorage.getItem('diagram_positions')
      if (savedPositions) {
        try {
          const positions: Record<string, { x: number; y: number }> = JSON.parse(savedPositions)
          createdNodes = createdNodes.map(n => ({
            ...n,
            position: positions[n.id] || n.position,
          }))
        } catch {
          // Ignore invalid positions data
        }
        sessionStorage.removeItem('diagram_positions')
      } else {
        createdNodes = getLayoutedNodes(createdNodes, createdEdges, 'TB')
      }

      const savedViewport = sessionStorage.getItem('diagram_viewport')
      if (savedViewport) {
        sessionStorage.removeItem('diagram_viewport')
      }

      const storedManualRels = sessionStorage.getItem('manual_relationships')
      if (storedManualRels) {
        try {
          const parsedRels: ManualRelationship[] = JSON.parse(storedManualRels)
          setManualRelationships(parsedRels)
        } catch {
          // Ignore invalid data
        }
      }

      // Load annotations
      const storedAnnotations = sessionStorage.getItem('diagram_annotations')
      if (storedAnnotations) {
        try {
          setAnnotations(JSON.parse(storedAnnotations))
        } catch {
          // Ignore invalid data
        }
      }

      // Load current diagram ID if opened from My Diagrams
      const storedDiagramId = sessionStorage.getItem('current_diagram_id')
      const storedDiagramName = sessionStorage.getItem('current_diagram_name')
      if (storedDiagramId) {
        setCurrentDiagramId(storedDiagramId)
        setCurrentDiagramName(storedDiagramName)
      }

      setNodes(createdNodes.map(n => ({ ...n, data: { ...n.data, onHideTable: handleHideTable } })))
      setEdges(createdEdges)
      setState('ready')
    } catch (err) {
      alert(`[Diagram ERROR] ${err instanceof Error ? err.message : String(err)}`)
      console.error('Failed to parse stored schema:', err)
      setState('empty')
    }
  }, [])

  // Edge hover handler
  const handleEdgeHover = (
    edgeId: string | null,
    sourceId?: string,
    targetId?: string
  ) => {
    if (edgeId && sourceId && targetId) {
      setHoveredEdge({ sourceId, targetId })
    } else {
      setHoveredEdge(null)
    }
  }

  // Build diagram data for saving (includes connection configs for auto-reconnect)
  const buildDiagramData = () => {
    const positions: Record<string, { x: number; y: number }> = {}
    for (const node of currentNodesRef.current) {
      positions[node.id] = { x: node.position.x, y: node.position.y }
    }
    const rawSchema = sessionStorage.getItem('extracted_schema')
    const parsedSchema = rawSchema ? JSON.parse(rawSchema) : schema

    // Gather connection configs for persistence
    const connectionConfigs: Record<string, unknown>[] = []
    try {
      const sqlCreds = JSON.parse(sessionStorage.getItem('db_credentials') || '{}')
      if (sqlCreds.host) {
        // postgres and sqlserver share the db_credentials key; db_type tells them apart.
        const dbType = sessionStorage.getItem('db_type') || 'sqlserver'
        connectionConfigs.push({
          type: dbType,
          host: sqlCreds.host,
          port: sqlCreds.port || (dbType === 'postgres' ? 5432 : 1433),
          database: sqlCreds.database,
          username: sqlCreds.username,
          password: sqlCreds.password, // Backend will encrypt this
        })
      }
    } catch { /* ignore */ }
    const bqProjectId = sessionStorage.getItem('bq_project_id')
    if (bqProjectId) {
      connectionConfigs.push({
        type: 'bigquery',
        project_id: bqProjectId,
      })
    }
    const dvEnvUrl = sessionStorage.getItem('dv_environment_url')
    if (dvEnvUrl) {
      connectionConfigs.push({
        type: 'dataverse',
        environment_url: dvEnvUrl,
      })
    }

    return {
      schema: parsedSchema,
      positions,
      viewport: { x: 0, y: 0, zoom: 1 },
      manualRelationships,
      annotations,
      connection_configs: connectionConfigs,
    }
  }

  // Quick save (update existing diagram)
  const handleQuickSave = async () => {
    if (!currentDiagramId || !currentDiagramName) return
    setIsSaving(true)
    try {
      const diagramData = buildDiagramData()
      await updateDiagram(currentDiagramId, currentDiagramName, diagramData)
      if (schema) {
        const sql = generateDDL(schema, manualRelationships)
        await saveDiagramSql(currentDiagramId, sql)
      }
      setSaveMessage('Saved!')
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to save diagram')
    } finally {
      setIsSaving(false)
    }
  }

  // Save as new diagram (always shows dialog)
  const handleSaveAs = async (name: string) => {
    setIsSaving(true)
    try {
      const diagramData = buildDiagramData()
      const metadata = await saveDiagram(name, diagramData)
      if (schema) {
        const sql = generateDDL(schema, manualRelationships)
        await saveDiagramSql(metadata.id, sql)
      }
      // Update current diagram tracking to the new one
      setCurrentDiagramId(metadata.id)
      setCurrentDiagramName(name)
      sessionStorage.setItem('current_diagram_id', metadata.id)
      sessionStorage.setItem('current_diagram_name', name)
      setShowSaveDialog(false)
      setSaveMessage('Saved as new!')
      setTimeout(() => setSaveMessage(null), 3000)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to save diagram')
    } finally {
      setIsSaving(false)
    }
  }

  // Save button click handler
  const handleSaveClick = () => {
    if (currentDiagramId) {
      // Existing diagram — quick save
      handleQuickSave()
    } else {
      // New diagram — show dialog
      setShowSaveDialog(true)
    }
  }

  // --- Annotation handlers ---
  const handleAddAnnotation = useCallback((partial: Omit<Annotation, 'id' | 'created_at' | 'updated_at' | 'created_by'>) => {
    const now = new Date().toISOString()
    const annotation: Annotation = {
      id: crypto.randomUUID(),
      ...partial,
      created_at: now,
      updated_at: now,
      created_by: 'me', // replaced with session email in buildDiagramData
    }
    setAnnotations((prev) => {
      const updated = [...prev, annotation]
      sessionStorage.setItem('diagram_annotations', JSON.stringify(updated))
      return updated
    })
  }, [])

  const handleDeleteAnnotation = useCallback((id: string) => {
    setAnnotations((prev) => {
      const updated = prev.filter((a) => a.id !== id)
      sessionStorage.setItem('diagram_annotations', JSON.stringify(updated))
      return updated
    })
  }, [])

  const handleUpdateAnnotation = useCallback((id: string, text: string) => {
    setAnnotations((prev) => {
      const updated = prev.map((a) =>
        a.id === id ? { ...a, text, updated_at: new Date().toISOString() } : a
      )
      sessionStorage.setItem('diagram_annotations', JSON.stringify(updated))
      return updated
    })
  }, [])

  // --- Share handlers ---
  const handleShare = useCallback(async (): Promise<string> => {
    if (!currentDiagramId) throw new Error('Save the diagram first to share it')
    const result = await shareDiagram(currentDiagramId)
    if (result.error || !result.share_token) {
      throw new Error(result.error || 'Failed to share diagram')
    }
    setShareToken(result.share_token)
    return result.share_token
  }, [currentDiagramId])

  // Build a pipeline from THIS schema: ensure a share token (that token is the
  // catalog source id), then open the embedded az_agent builder — one place.
  const handleBuildPipeline = useCallback(async () => {
    if (!currentDiagramId) {
      alert('Save the diagram first, then Build Pipeline.')
      return
    }
    try {
      const token = shareToken ?? (await handleShare())
      window.location.href = `/pipelines?token=${encodeURIComponent(token)}`
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not start the pipeline builder')
    }
  }, [currentDiagramId, shareToken, handleShare])

  const handleUnshare = useCallback(async () => {
    if (!currentDiagramId) return
    const result = await unshareDiagram(currentDiagramId)
    if (!result.success) {
      throw new Error(result.error || 'Failed to revoke share link')
    }
    setShareToken(null)
    setShareSettings({ showRelationships: false, shareNote: '' })
  }, [currentDiagramId])

  const handleUpdateShareSettings = useCallback(async (settings: { showRelationships: boolean; shareNote: string }) => {
    if (!currentDiagramId) return
    const result = await updateShareSettings(currentDiagramId, settings.showRelationships, settings.shareNote)
    if (!result.success) {
      throw new Error(result.error || 'Failed to update share settings')
    }
    setShareSettings(settings)
  }, [currentDiagramId])

  // Compute highlighted nodes: hovered edge > selected edge > advisor preview
  const highlightedNodes = useMemo(() => {
    if (hoveredEdge) {
      return new Set([hoveredEdge.sourceId, hoveredEdge.targetId])
    }
    if (selectedEdge) {
      return new Set([selectedEdge.sourceId, selectedEdge.targetId])
    }
    if (advisorHighlightedTables && advisorHighlightedTables.size > 0) {
      const nodeIds = new Set<string>()
      for (const tableName of advisorHighlightedTables) {
        for (const node of nodes) {
          if (node.data.table_name === tableName) {
            nodeIds.add(node.id)
          }
        }
      }
      return nodeIds.size > 0 ? nodeIds : null
    }
    return null
  }, [hoveredEdge, selectedEdge, advisorHighlightedTables, nodes])

  const totalRelationships = (schema?.foreign_keys.length || 0) + manualRelationships.length

  // Toolbar items
  const toolbarItems = useMemo(() => [
    // --- Data ---
    {
      id: 'add-dataset',
      label: 'Add Data Source',
      group: 'data',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      ),
      onClick: () => setShowAddDataset(true),
    },
    {
      id: 'relationships',
      label: 'Relationships',
      group: 'data',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      ),
      onClick: () => setShowRelationships(true),
      badge: totalRelationships || undefined,
    },
    {
      id: 'start-over',
      label: 'Start Over',
      group: 'data',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="1 4 1 10 7 10" />
          <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
        </svg>
      ),
      onClick: () => { window.location.href = '/' },
    },
    // --- View ---
    {
      id: 'auto-layout',
      label: 'Auto Layout',
      group: 'view',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" />
          <rect x="14" y="3" width="7" height="7" />
          <rect x="3" y="14" width="7" height="7" />
          <rect x="14" y="14" width="7" height="7" />
        </svg>
      ),
      onClick: handleAutoLayout,
    },
    {
      id: 'view-sql',
      label: 'View SQL',
      group: 'view',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      ),
      onClick: () => setShowSqlViewer(true),
    },
    {
      id: 'data-dictionary',
      label: 'Data Dictionary',
      group: 'view',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
          <line x1="8" y1="7" x2="16" y2="7" />
          <line x1="8" y1="11" x2="14" y2="11" />
        </svg>
      ),
      onClick: () => { window.location.href = '/dictionary' },
    },
    {
      id: 'lineage',
      label: 'Data Lineage',
      group: 'view',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="5" cy="6" r="3" /><circle cx="19" cy="6" r="3" /><circle cx="12" cy="18" r="3" />
          <line x1="5" y1="9" x2="12" y2="15" /><line x1="19" y1="9" x2="12" y2="15" />
        </svg>
      ),
      onClick: () => setShowLineage(true),
    },
    // --- AI Tools ---
    {
      id: 'auto-document',
      label: isAutoDocumenting ? 'Documenting...' : 'Auto Document',
      group: 'ai',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <line x1="10" y1="9" x2="8" y2="9" />
        </svg>
      ),
      onClick: handleAutoDocument,
      disabled: isAutoDocumenting || !schema,
    },
    {
      id: 'infer-relationships',
      label: 'Infer Relationships',
      group: 'ai',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>
      ),
      onClick: () => setShowInferRelationships(true),
    },
    {
      id: 'impact-analysis',
      label: 'Impact Analysis',
      group: 'ai',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
      onClick: () => setShowImpactAnalysis(true),
    },
    {
      id: 'ai-advisor',
      label: 'Talk to your Data',
      group: 'ai',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      ),
      onClick: () => { window.location.href = '/chat' },
    },
    // --- Collaborate ---
    {
      id: 'share',
      label: shareToken ? 'Shared' : 'Share',
      group: 'collaborate',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" /><line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
      ),
      onClick: () => {
        if (!currentDiagramId) {
          alert('Save the diagram first before sharing.')
          return
        }
        setShowShareDialog(true)
      },
    },
    {
      id: 'annotations',
      label: 'Annotations',
      group: 'collaborate',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
      ),
      onClick: () => setShowAnnotations(true),
      badge: annotations.length || undefined,
    },
    {
      id: 'schema-history',
      label: 'Change History',
      group: 'collaborate',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
      ),
      onClick: () => setShowHistory(true),
    },
    // --- Navigate ---
    {
      id: 'export-pdf',
      label: 'Export PDF',
      group: 'navigate',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="12" y1="18" x2="12" y2="12" />
          <polyline points="9 15 12 18 15 15" />
        </svg>
      ),
      onClick: handleExportPdf,
      disabled: isExporting,
    },
    {
      id: 'my-diagrams',
      label: 'My Diagrams',
      group: 'navigate',
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      ),
      onClick: () => { window.location.href = '/diagrams' },
    },
  ], [handleExportPdf, isExporting, handleAutoLayout, totalRelationships, handleAutoDocument, isAutoDocumenting, schema, annotations.length, shareToken, currentDiagramId])

  // Loading state
  if (state === 'loading') {
    return (
      <main className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Loading diagram...</p>
        </div>
      </main>
    )
  }

  // Empty state
  if (state === 'empty') {
    return (
      <main className="min-h-screen bg-gray-50 py-12">
        <div className="container mx-auto px-4 max-w-lg">
          <div className="bg-white rounded-lg shadow-md p-8 text-center">
            <div className="mx-auto w-16 h-16 rounded-full bg-yellow-100 flex items-center justify-center mb-6">
              <svg className="w-8 h-8 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">No Schema Found</h1>
            <p className="text-gray-600 mb-6">
              You need to extract a database schema before viewing the diagram.
            </p>
            <a
              href="/"
              className="inline-block px-6 py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors font-medium"
            >
              Connect to Database
            </a>
          </div>
        </div>
      </main>
    )
  }

  // Ready state
  return (
    <main className="h-screen flex flex-col">
      {/* Header */}
      <header className="glass-panel px-4 py-2.5 flex items-center justify-between flex-shrink-0 relative z-30 border-b border-white/10">
        <div className="flex items-center gap-4">
          <div className="border-r border-slate-700/80 pr-4">
            <ZionLogo className="h-7 text-white drop-shadow-[0_0_15px_rgba(79,70,229,0.4)]" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wide">
              {schema?.database_name || 'Database'}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-xs text-white/60">
                {schema?.table_count} tables, {totalRelationships} relationships
                {manualRelationships.length > 0 ? ` (${manualRelationships.length} manual)` : ''}
              </p>
              {loadedDatasets.length > 1 && (
                <div className="flex items-center gap-1">
                  {loadedDatasets.map((ds) => (
                    <span
                      key={ds}
                      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium bg-white/10 text-white/80 rounded-full"
                    >
                      {ds.length > 20 ? ds.slice(0, 20) + '…' : ds}
                      <button
                        onClick={() => {
                          if (window.confirm(`Remove dataset "${ds}" and all its tables/relationships?`)) {
                            handleRemoveDataset(ds)
                          }
                        }}
                        className="ml-0.5 text-white/40 hover:text-red-400 transition-colors"
                        title={`Remove ${ds}`}
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {saveMessage && (
            <span className="text-xs text-emerald-300 font-medium">{saveMessage}</span>
          )}
          <button
            onClick={handleSaveClick}
            disabled={isSaving}
            className="px-4 py-1.5 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 transition-all disabled:opacity-50 shadow-[0_0_10px_rgba(79,70,229,0.5)] font-medium"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          {currentDiagramId && (
            <button
              onClick={() => setShowSaveDialog(true)}
              className="px-3 py-1.5 text-sm bg-slate-800 border border-slate-700 text-slate-300 rounded-lg hover:bg-slate-700 hover:text-white transition-colors shadow-sm"
            >
              Save As
            </button>
          )}
          <button
            onClick={handleBuildPipeline}
            className="px-4 py-1.5 text-sm bg-emerald-600 border border-emerald-500/50 text-white rounded-lg hover:bg-emerald-500 transition-all shadow-[0_0_10px_rgba(16,185,129,0.5)] font-medium whitespace-nowrap"
          >
            🔧 Build Pipeline
          </button>
          <div className="border-l border-white/20 pl-2 ml-1">
            <UserMenu />
          </div>
        </div>
      </header>

      {/* Cross-dataset suggestions banner */}
      {crossDatasetBanner && crossDatasetBanner.length > 0 && (
        <div className="bg-indigo-900/40 border-b border-indigo-500/30 backdrop-blur-md px-4 py-2 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-indigo-200">
              Found <strong>{crossDatasetBanner.length}</strong> potential cross-dataset relationship{crossDatasetBanner.length !== 1 ? 's' : ''}.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleAcceptSuggestions}
              className="px-3 py-1 text-sm bg-indigo-600 text-white border border-indigo-500/50 rounded-md hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.5)] transition-colors"
            >
              Add All
            </button>
            <button
              onClick={() => setCrossDatasetBanner(null)}
              className="px-3 py-1 text-sm text-slate-300 bg-slate-800 border border-slate-700 rounded-md hover:bg-slate-700 transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Main content: toolbar + canvas + advisor */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left toolbar */}
        <Toolbar items={toolbarItems} />

        {/* Diagram canvas */}
        <div className="flex-1 relative">
          {/* Before/After toggle */}
          {previewMode && (
            <SchemaPreviewToggle
              activeView={previewView}
              onToggle={setPreviewView}
              appliedCount={previewAppliedCount}
              totalCount={previewTotalCount}
              onConfirm={handleConfirmPreview}
              onDiscard={handleDiscardPreview}
            />
          )}

          <DiagramCanvas
            initialNodes={previewMode && previewView === 'after' ? previewNodes : nodes}
            initialEdges={previewMode && previewView === 'after' ? previewEdges : edges}
            highlightedNodes={highlightedNodes}
            onEdgeHover={handleEdgeHover}
            onEdgeClick={(_edgeId, sourceId, targetId) => setSelectedEdge({ sourceId, targetId })}
            onPaneClick={() => setSelectedEdge(null)}
            onNodesUpdate={handleNodesUpdate}
            autoLayoutTrigger={layoutTrigger}
            manualEdges={previewMode && previewView === 'after' ? [] : manualEdges}
            onAddManualRelationship={handleAddManualRelationship}
            onDeleteManualRelationship={handleDeleteManualRelationship}
            tables={previewMode && previewView === 'after' ? previewSchema?.tables : schema?.tables}
          />

          {/* Hidden Tables floating panel */}
          {hiddenTables.size > 0 && (
            <HiddenTablesPanel
              hiddenTables={hiddenTables}
              schema={schema}
              onRestore={handleRestoreTable}
              onRestoreAll={handleRestoreAllTables}
            />
          )}
        </div>

        {/* AI Advisor moved to /chat full-page route */}
      </div>

      {/* SQL Viewer modal */}
      {schema && (
        <SqlViewer
          isOpen={showSqlViewer}
          onClose={() => setShowSqlViewer(false)}
          sql={generateDDL(schema, manualRelationships)}
          databaseName={schema.database_name}
        />
      )}

      {/* Save dialog */}
      <SaveDialog
        isOpen={showSaveDialog}
        onClose={() => setShowSaveDialog(false)}
        onSave={handleSaveAs}
        defaultName={schema?.database_name || 'My Diagram'}
        isSaving={isSaving}
      />

      {/* Add Data Source modal */}
      <AddDataSourceModal
        isOpen={showAddDataset}
        onClose={() => setShowAddDataset(false)}
        loadedDatasets={loadedDatasets}
        onAdd={handleAddDataset}
      />

      {/* Relationships panel */}
      <RelationshipsPanel
        isOpen={showRelationships}
        onClose={() => setShowRelationships(false)}
        autoRelationships={schema?.foreign_keys || []}
        manualRelationships={manualRelationships}
        onDeleteManual={handleDeleteManualRelationship}
        onDeleteAuto={handleDeleteAutoRelationship}
        onClearAllManual={() => {
          setManualRelationships([])
          sessionStorage.removeItem('manual_relationships')
        }}
        onHighlightEdge={(sourceId, targetId) => setHoveredEdge({ sourceId, targetId })}
        onClearHighlight={() => setHoveredEdge(null)}
      />

      {/* AI Infer Relationships modal */}
      <InferRelationshipsPanel
        isOpen={showInferRelationships}
        onClose={() => setShowInferRelationships(false)}
        schema={schema}
        onAccept={handleAcceptInferredRelationship}
      />

      {/* Share dialog */}
      <ShareDialog
        isOpen={showShareDialog}
        onClose={() => setShowShareDialog(false)}
        shareToken={shareToken}
        diagramName={currentDiagramName || schema?.database_name || 'Diagram'}
        shareSettings={shareSettings}
        onShare={handleShare}
        onUnshare={handleUnshare}
        onUpdateSettings={handleUpdateShareSettings}
      />

      {/* Annotations panel */}
      <AnnotationsPanel
        isOpen={showAnnotations}
        onClose={() => setShowAnnotations(false)}
        annotations={annotations}
        onAdd={handleAddAnnotation}
        onDelete={handleDeleteAnnotation}
        onUpdate={handleUpdateAnnotation}
        schema={schema}
        userEmail="me"
      />

      {/* Impact Analysis panel */}
      <ImpactAnalysisPanel
        isOpen={showImpactAnalysis}
        onClose={() => setShowImpactAnalysis(false)}
        schema={schema}
      />

      {/* Schema Change History panel */}
      <SchemaHistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        diagramId={currentDiagramId}
      />

      {/* Data Lineage panel */}
      <LineagePanel
        isOpen={showLineage}
        onClose={() => setShowLineage(false)}
        schema={schema}
        manualRelationships={manualRelationships}
      />

      {/* Floating Schema Advisor chat */}
      {schema && (
        <FloatingChat schema={schema} onSchemaChange={handleSchemaChange} />
      )}
    </main>
  )
}
