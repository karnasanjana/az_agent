// frontend/src/types/diagram.ts
// React Flow types for ER diagram visualization

import type { Node, Edge } from '@xyflow/react'
import type { Table, ForeignKey } from './schema'

/**
 * Data payload for table nodes in the diagram.
 * Extends the Table interface from schema extraction.
 * Index signature required by React Flow's Record<string, unknown> constraint.
 */
export interface TableNodeData extends Table {
  // Table data is inherited from Table interface:
  // - object_id: number
  // - schema_name: string
  // - table_name: string
  // - columns: Column[]
  // - indexes: Index[]

  // Set of column names that are foreign keys in this table
  fkColumns: Set<string>

  // Color for the dataset this table belongs to (multi-dataset mode)
  datasetColor?: string

  // Index signature for React Flow compatibility
  [key: string]: unknown
}

/**
 * Custom node type for tables in React Flow.
 * Position and dimensions managed by React Flow, data contains table info.
 */
export type TableNode = Node<TableNodeData, 'tableNode'>

/**
 * Cardinality information inferred from FK constraints.
 * Used to display relationship labels on edge hover.
 */
export interface CardinalityInfo {
  cardinality: '1:1' | '1:N'
  optionality: 'required' | 'optional'
  sourceLabel: string  // Display label near source (child) node: '*', '0..*', '1', '0..1'
  targetLabel: string  // Display label near target (parent) node: always '1'
  tooltip: string      // Human-readable: "Many to One (required)"
}

/**
 * Data payload for relationship edges between tables.
 * Contains FK constraint information for edge rendering.
 * Index signature required by React Flow's Record<string, unknown> constraint.
 */
export interface RelationshipEdgeData {
  foreignKey: ForeignKey
  // Color assigned based on constraint (for visual differentiation)
  color?: string
  // Inferred cardinality for hover display
  cardinalityInfo?: CardinalityInfo
  // Index signature for React Flow compatibility
  [key: string]: unknown
}

/**
 * Custom edge type for FK relationships in React Flow.
 * Source/target and connection info managed by React Flow, data contains FK info.
 */
export type RelationshipEdge = Edge<RelationshipEdgeData, 'relationship'>

/**
 * Metadata for a saved diagram (returned from list/save operations).
 */
export interface DiagramMetadata {
  id: string
  name: string
  created_at: string
  updated_at: string
  table_count: number
  database_name: string
  share_token?: string | null
}

/**
 * A user annotation on a table or column in the diagram.
 */
export interface Annotation {
  id: string
  target_type: 'table' | 'column'
  target_table: string  // schema_name.table_name
  target_column?: string | null
  text: string
  created_at: string
  created_by: string
  updated_at: string
}

/**
 * Impact analysis result for a table or column change.
 */
export interface ImpactAnalysisResult {
  target: { table: string; column: string | null }
  direct_dependencies: ImpactDependency[]
  indirect_dependencies: ImpactDependency[]
  total_impact_count: number
  risk: { level: 'low' | 'medium' | 'high'; message: string } | null
}

export interface ImpactDependency {
  type: string
  table: string
  columns?: string[]
  constraint: string
  relationship?: string
  via?: string
}

/**
 * A single schema change entry from the change history.
 */
export interface SchemaChangeEntry {
  version: number
  timestamp: string
  summary: string
  added_tables: string[]
  removed_tables: string[]
  modified_tables: { table: string; changes: string[] }[]
  added_foreign_keys: string[]
  removed_foreign_keys: string[]
}

/**
 * A manually-defined relationship between two tables.
 * Used for databases (e.g. BigQuery) that have no FK constraints.
 */
export interface ManualRelationship {
  id: string
  source_database: string
  source_table: string
  source_column: string
  target_database: string
  target_table: string
  target_column: string
}

/**
 * A suggested cross-dataset relationship detected by column name matching.
 */
export interface SuggestedRelationship {
  id: string
  sourceDataset: string
  sourceTable: string
  sourceColumn: string
  targetDataset: string
  targetTable: string
  targetColumn: string
  confidence: 'high' | 'medium'
}

/**
 * An AI-inferred FK relationship returned by the infer-relationships endpoint.
 * Confidence is 0..1; UI buckets it as high (>0.8), medium (0.5-0.8), low (<0.5).
 */
export interface InferredRelationship {
  source_table: string
  source_schema: string
  source_column: string
  target_table: string
  target_schema: string
  target_column: string
  confidence: number
  reason: string
}

/**
 * The data payload saved with a diagram (schema + layout state).
 */
export interface SavedDiagramData {
  schema: import('./schema').DatabaseSchema
  positions: Record<string, { x: number; y: number }>
  viewport: { x: number; y: number; zoom: number }
  manualRelationships?: ManualRelationship[]
  annotations?: Annotation[]
}
