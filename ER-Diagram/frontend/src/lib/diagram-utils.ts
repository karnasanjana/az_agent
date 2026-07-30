// frontend/src/lib/diagram-utils.ts
// Utility functions for converting schema to React Flow nodes and edges

import type { Node, Edge } from '@xyflow/react'
import type { Table, ForeignKey } from '@/types/schema'
import type { TableNodeData, RelationshipEdgeData, CardinalityInfo, ManualRelationship, SuggestedRelationship } from '@/types/diagram'

/**
 * Color palette for foreign key relationships.
 * Each FK constraint gets a distinct color cycling through this array.
 */
export const FK_COLORS = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
]

/**
 * Color palette for dataset headers in multi-dataset mode.
 * Each dataset gets a distinct color cycling through this array.
 */
export const DATASET_COLORS = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
]

/**
 * Get the header color for a dataset based on its position in the dataset list.
 */
export function getDatasetColor(datasetName: string, allDatasets: string[]): string {
  const index = allDatasets.indexOf(datasetName)
  return DATASET_COLORS[index >= 0 ? index % DATASET_COLORS.length : 0]
}

/**
 * Transform extracted tables into React Flow nodes.
 * All nodes start at position {0,0}; actual positioning is handled
 * by getLayoutedNodes() in the caller.
 *
 * @param tables - Array of Table objects from schema extraction
 * @param foreignKeys - Array of ForeignKey objects to derive FK columns per table
 * @returns Array of React Flow Node objects with TableNodeData
 */
export function schemaToNodes(
  tables: Table[],
  foreignKeys: ForeignKey[],
  datasetColors?: Record<string, string>
): Node<TableNodeData>[] {
  // Build a lookup: Map<schema.table, Set<column_names>> for FK columns
  const fkColumnMap = new Map<string, Set<string>>()
  for (const fk of foreignKeys) {
    const tableKey = `${fk.source_schema}.${fk.source_table}`
    if (!fkColumnMap.has(tableKey)) {
      fkColumnMap.set(tableKey, new Set())
    }
    // Add all source columns from this FK constraint
    for (const col of fk.source_columns) {
      fkColumnMap.get(tableKey)!.add(col)
    }
  }

  return tables.map((table) => {
    // Node ID: schema_name.table_name for unique identification
    const nodeId = `${table.schema_name}.${table.table_name}`

    return {
      id: nodeId,
      type: 'tableNode',
      position: { x: 0, y: 0 },
      data: {
        ...table,
        fkColumns: fkColumnMap.get(nodeId) || new Set<string>(),
        datasetColor: datasetColors?.[table.schema_name],
      } as TableNodeData,
    }
  })
}

/**
 * Infer cardinality information from a foreign key constraint.
 * Checks source table indexes for uniqueness (1:1 vs 1:N) and
 * source column nullability (required vs optional).
 *
 * @param fk - Foreign key constraint
 * @param tables - All tables for looking up source table metadata
 * @returns CardinalityInfo with labels and tooltip
 */
export function inferCardinality(
  fk: ForeignKey,
  tables: Table[]
): CardinalityInfo {
  const sourceTable = tables.find(
    t => t.schema_name === fk.source_schema && t.table_name === fk.source_table
  )

  // Check if FK source columns have a unique constraint on source table
  // If source columns are unique -> 1:1, else -> 1:N
  const sourceColumnsUnique = sourceTable?.indexes.some(
    idx => idx.is_unique &&
           idx.columns.length === fk.source_columns.length &&
           fk.source_columns.every(col => idx.columns.includes(col))
  ) ?? false

  // Check if FK source columns are nullable -> optional
  const fkColumnsNullable = fk.source_columns.every(col => {
    const column = sourceTable?.columns.find(c => c.name === col)
    return column?.is_nullable ?? false
  })

  const cardinality = sourceColumnsUnique ? '1:1' as const : '1:N' as const
  const optionality = fkColumnsNullable ? 'optional' as const : 'required' as const

  // Source label (child side): depends on uniqueness and optionality
  let sourceLabel: string
  if (sourceColumnsUnique) {
    sourceLabel = fkColumnsNullable ? '0..1' : '1'
  } else {
    sourceLabel = fkColumnsNullable ? '0..*' : '*'
  }

  // Target label (parent side): always '1' (FK references PK/unique)
  const targetLabel = '1'

  // Human-readable tooltip
  const cardinalityText = sourceColumnsUnique ? 'One to One' : 'Many to One'
  const optionalityText = fkColumnsNullable ? 'optional' : 'required'
  const tooltip = `${cardinalityText} (${optionalityText})`

  return { cardinality, optionality, sourceLabel, targetLabel, tooltip }
}

/**
 * Transform foreign keys into React Flow edges.
 * Each edge connects source table to target table with relationship data.
 * Enriches edge data with inferred cardinality information.
 *
 * @param foreignKeys - Array of ForeignKey objects from schema extraction
 * @param tables - Array of Table objects for cardinality inference
 * @returns Array of React Flow Edge objects with RelationshipEdgeData
 */
export function schemaToEdges(
  foreignKeys: ForeignKey[],
  tables: Table[]
): Edge<RelationshipEdgeData>[] {
  return foreignKeys.map((fk, index) => {
    // Source and target node IDs match the format from schemaToNodes
    const sourceId = `${fk.source_schema}.${fk.source_table}`
    const targetId = `${fk.target_schema}.${fk.target_table}`

    // Cycle through color palette for visual differentiation
    const color = FK_COLORS[index % FK_COLORS.length]

    // Infer cardinality from FK constraints and table metadata
    const cardinalityInfo = inferCardinality(fk, tables)

    return {
      id: fk.constraint_name,
      source: sourceId,
      target: targetId,
      type: 'relationship',
      data: {
        foreignKey: fk,
        color,
        cardinalityInfo,
      },
      style: {
        stroke: color,
      },
    }
  })
}

/**
 * Convert manual relationships to React Flow edges.
 * Manual edges use dashed gray styling and the 'manualRelationship' edge type.
 *
 * @param relationships - Array of ManualRelationship objects
 * @returns Array of React Flow Edge objects for manual relationships
 */
export function manualRelationshipsToEdges(
  relationships: ManualRelationship[]
): Edge[] {
  return relationships.map((rel) => ({
    id: rel.id,
    source: `${rel.source_database}.${rel.source_table}`,
    target: `${rel.target_database}.${rel.target_table}`,
    type: 'manualRelationship',
    data: { relationship: rel },
    style: { stroke: '#6B7280', strokeDasharray: '8 4' },
    animated: false,
  }))
}

/**
 * Detect potential cross-dataset relationships by matching column names.
 *
 * Matching rules:
 * - High confidence: column `foo_id` in table A matches table `foo` or `foos`
 *   in another dataset that has an `id` or `foo_id` column.
 * - Medium confidence: exact column name match across datasets
 *   (e.g., both tables have `student_id`).
 * - Only cross-dataset matches (same-dataset FKs are already handled).
 *
 * @param tables - All tables across all loaded datasets
 * @returns Array of suggested relationships
 */
export function detectCrossDatasetRelationships(
  tables: Table[]
): SuggestedRelationship[] {
  const suggestions: SuggestedRelationship[] = []
  const seen = new Set<string>()

  // Group tables by dataset (schema_name)
  const datasetTables = new Map<string, Table[]>()
  for (const table of tables) {
    const existing = datasetTables.get(table.schema_name) || []
    existing.push(table)
    datasetTables.set(table.schema_name, existing)
  }

  const datasets = Array.from(datasetTables.keys())
  if (datasets.length < 2) return suggestions

  // Build a lookup: dataset -> table_name (lowered) -> Table
  const tableByName = new Map<string, Map<string, Table>>()
  for (const [ds, tbls] of datasetTables) {
    const map = new Map<string, Table>()
    for (const t of tbls) {
      map.set(t.table_name.toLowerCase(), t)
    }
    tableByName.set(ds, map)
  }

  // Build a lookup: dataset -> table_name -> Set<column_name (lowered)>
  const columnSets = new Map<string, Map<string, Set<string>>>()
  for (const [ds, tbls] of datasetTables) {
    const dsMap = new Map<string, Set<string>>()
    for (const t of tbls) {
      dsMap.set(t.table_name, new Set(t.columns.map(c => c.name.toLowerCase())))
    }
    columnSets.set(ds, dsMap)
  }

  for (const [sourceDs, sourceTables] of datasetTables) {
    for (const sourceTable of sourceTables) {
      for (const col of sourceTable.columns) {
        const colLower = col.name.toLowerCase()

        // Check for _id or Id suffix pattern
        let baseName: string | null = null
        if (colLower.endsWith('_id') && colLower.length > 3) {
          baseName = colLower.slice(0, -3)
        } else if (col.name.endsWith('Id') && col.name.length > 2) {
          baseName = col.name.slice(0, -2).toLowerCase()
        }

        // High confidence: foo_id -> table foo/foos in other dataset
        if (baseName) {
          for (const [targetDs, targetTableMap] of tableByName) {
            if (targetDs === sourceDs) continue

            // Look for table named `baseName` or `baseName + 's'`
            const candidates = [baseName, baseName + 's']
            for (const candidateName of candidates) {
              const targetTable = targetTableMap.get(candidateName)
              if (!targetTable) continue

              // Check if target table has 'id' or the same column name
              const targetCols = columnSets.get(targetDs)?.get(targetTable.table_name)
              if (!targetCols) continue

              let matchedCol: string | null = null
              if (targetCols.has('id')) {
                matchedCol = 'id'
              } else if (targetCols.has(colLower)) {
                matchedCol = col.name
              }

              if (matchedCol) {
                const key = `${sourceDs}.${sourceTable.table_name}.${col.name}->${targetDs}.${targetTable.table_name}.${matchedCol}`
                const reverseKey = `${targetDs}.${targetTable.table_name}.${matchedCol}->${sourceDs}.${sourceTable.table_name}.${col.name}`
                if (!seen.has(key) && !seen.has(reverseKey)) {
                  seen.add(key)
                  suggestions.push({
                    id: `suggested_${key}`,
                    sourceDataset: sourceDs,
                    sourceTable: sourceTable.table_name,
                    sourceColumn: col.name,
                    targetDataset: targetDs,
                    targetTable: targetTable.table_name,
                    targetColumn: matchedCol,
                    confidence: 'high',
                  })
                }
              }
            }
          }
        }

        // Medium confidence: exact column name match across datasets
        if (colLower.endsWith('_id') || colLower.endsWith('id')) {
          for (const [targetDs, targetTables] of datasetTables) {
            if (targetDs === sourceDs) continue

            for (const targetTable of targetTables) {
              const targetCols = columnSets.get(targetDs)?.get(targetTable.table_name)
              if (!targetCols || !targetCols.has(colLower)) continue

              const key = `${sourceDs}.${sourceTable.table_name}.${col.name}->${targetDs}.${targetTable.table_name}.${col.name}`
              const reverseKey = `${targetDs}.${targetTable.table_name}.${col.name}->${sourceDs}.${sourceTable.table_name}.${col.name}`
              if (!seen.has(key) && !seen.has(reverseKey)) {
                seen.add(key)
                suggestions.push({
                  id: `suggested_${key}`,
                  sourceDataset: sourceDs,
                  sourceTable: sourceTable.table_name,
                  sourceColumn: col.name,
                  targetDataset: targetDs,
                  targetTable: targetTable.table_name,
                  targetColumn: col.name,
                  confidence: 'medium',
                })
              }
            }
          }
        }
      }
    }
  }

  return suggestions
}
