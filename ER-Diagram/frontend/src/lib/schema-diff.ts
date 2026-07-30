// Schema diff utilities — apply and revert structural changes

import type { DatabaseSchema, Table, Column, ForeignKey } from '@/types/schema'
import type { SchemaChange, Suggestion } from '@/types/chat'

/**
 * Deep clone a schema to create a snapshot for undo.
 */
export function cloneSchema(schema: DatabaseSchema): DatabaseSchema {
  return JSON.parse(JSON.stringify(schema))
}

/**
 * Apply a single change to the schema, returning the modified schema.
 */
function applyChange(schema: DatabaseSchema, change: SchemaChange): DatabaseSchema {
  const s = cloneSchema(schema)

  switch (change.action) {
    case 'remove_table': {
      const tableName = change.table
      const schemaName = change.schema_name
      s.tables = s.tables.filter(
        (t) => !(t.table_name === tableName && (!schemaName || t.schema_name === schemaName))
      )
      // Remove relationships involving this table
      s.foreign_keys = s.foreign_keys.filter(
        (fk) => fk.source_table !== tableName && fk.target_table !== tableName
      )
      s.table_count = s.tables.length
      break
    }

    case 'add_table': {
      if (change.table) {
        const newTable: Table = {
          object_id: Date.now(),
          schema_name: change.schema_name || s.tables[0]?.schema_name || 'dbo',
          table_name: change.table,
          columns: (change.columns || []).map((c) => ({
            name: c.name,
            data_type: c.data_type,
            is_nullable: c.is_nullable ?? true,
            is_primary_key: false,
            is_identity: false,
          })),
          indexes: [],
          is_view: false,
        }
        s.tables.push(newTable)
        s.table_count = s.tables.length
      }
      break
    }

    case 'merge_table': {
      const sourceTable = s.tables.find((t) => t.table_name === change.source_table)
      const targetTable = s.tables.find((t) => t.table_name === change.target_table)
      if (sourceTable && targetTable) {
        // Move all non-duplicate columns from source to target
        const targetColNames = new Set(targetTable.columns.map((c) => c.name))
        for (const col of sourceTable.columns) {
          if (!targetColNames.has(col.name)) {
            targetTable.columns.push({ ...col })
          }
        }
        // Remove the source table
        s.tables = s.tables.filter((t) => t.table_name !== change.source_table)
        // Update relationships: redirect references to source table → target table
        for (const fk of s.foreign_keys) {
          if (fk.source_table === change.source_table) {
            fk.source_table = change.target_table!
          }
          if (fk.target_table === change.source_table) {
            fk.target_table = change.target_table!
          }
        }
        // Remove self-referencing FKs created by the merge
        s.foreign_keys = s.foreign_keys.filter(
          (fk) => fk.source_table !== fk.target_table || fk.source_table !== change.target_table
        )
        s.table_count = s.tables.length
      }
      break
    }

    case 'add_column': {
      const table = s.tables.find(
        (t) => t.table_name === change.table && (!change.schema_name || t.schema_name === change.schema_name)
      )
      if (table && change.column) {
        table.columns.push({
          name: change.column,
          data_type: change.data_type || 'varchar',
          is_nullable: change.is_nullable ?? true,
          is_primary_key: false,
          is_identity: false,
        })
      }
      break
    }

    case 'remove_column': {
      const table = s.tables.find(
        (t) => t.table_name === change.table && (!change.schema_name || t.schema_name === change.schema_name)
      )
      if (table && change.column) {
        table.columns = table.columns.filter((c) => c.name !== change.column)
      }
      break
    }

    case 'move_column': {
      const fromTable = s.tables.find((t) => t.table_name === change.from_table)
      const toTable = s.tables.find((t) => t.table_name === change.to_table)
      if (fromTable && toTable && change.column) {
        const col = fromTable.columns.find((c) => c.name === change.column)
        if (col) {
          fromTable.columns = fromTable.columns.filter((c) => c.name !== change.column)
          toTable.columns.push({ ...col })
        }
      }
      break
    }

    case 'add_relationship': {
      if (change.source_table && change.target_table && change.source_columns && change.target_columns) {
        // Look up actual schema names from tables if not explicitly provided
        const sourceTable = s.tables.find((t) => t.table_name === change.source_table &&
          (!change.source_schema || t.schema_name === change.source_schema) &&
          (!change.schema_name || t.schema_name === change.schema_name))
          || s.tables.find((t) => t.table_name === change.source_table)
        const targetTable = s.tables.find((t) => t.table_name === change.target_table &&
          (!change.target_schema || t.schema_name === change.target_schema))
          || s.tables.find((t) => t.table_name === change.target_table)

        const newFk: ForeignKey = {
          constraint_name: change.constraint_name || `FK_${change.source_table}_${change.target_table}_${Date.now()}`,
          source_table: change.source_table,
          source_schema: change.source_schema || sourceTable?.schema_name || change.schema_name || s.tables[0]?.schema_name || 'dbo',
          source_columns: change.source_columns,
          target_table: change.target_table,
          target_schema: change.target_schema || targetTable?.schema_name || change.schema_name || s.tables[0]?.schema_name || 'dbo',
          target_columns: change.target_columns,
        }
        s.foreign_keys.push(newFk)
      }
      break
    }

    case 'remove_relationship': {
      if (change.constraint_name) {
        s.foreign_keys = s.foreign_keys.filter((fk) => fk.constraint_name !== change.constraint_name)
      }
      break
    }
  }

  // Recalculate standalone count
  const tablesWithFk = new Set<string>()
  for (const fk of s.foreign_keys) {
    tablesWithFk.add(`${fk.source_schema}.${fk.source_table}`)
    tablesWithFk.add(`${fk.target_schema}.${fk.target_table}`)
  }
  s.standalone_table_count = s.tables.filter(
    (t) => !tablesWithFk.has(`${t.schema_name}.${t.table_name}`)
  ).length

  return s
}

/**
 * Apply all changes from a suggestion to the schema.
 */
export function applySuggestion(schema: DatabaseSchema, suggestion: Suggestion): DatabaseSchema {
  let result = schema
  for (const change of suggestion.changes) {
    result = applyChange(result, change)
  }
  return result
}

/**
 * Get the set of table names affected by a suggestion (for highlighting).
 */
export function getAffectedTables(suggestion: Suggestion): Set<string> {
  const affected = new Set<string>()
  for (const change of suggestion.changes) {
    if (change.table) affected.add(change.table)
    if (change.source_table) affected.add(change.source_table)
    if (change.target_table) affected.add(change.target_table)
    if (change.from_table) affected.add(change.from_table)
    if (change.to_table) affected.add(change.to_table)
  }
  return affected
}

/**
 * Categorize changes in a suggestion for display.
 */
export function categorizeSuggestionChanges(suggestion: Suggestion): {
  removedTables: string[]
  addedTables: string[]
  modifiedTables: string[]
  addedColumns: { table: string; column: string }[]
  removedColumns: { table: string; column: string }[]
  movedColumns: { column: string; from: string; to: string }[]
  addedRelationships: { source: string; target: string }[]
  removedRelationships: string[]
} {
  const result = {
    removedTables: [] as string[],
    addedTables: [] as string[],
    modifiedTables: [] as string[],
    addedColumns: [] as { table: string; column: string }[],
    removedColumns: [] as { table: string; column: string }[],
    movedColumns: [] as { column: string; from: string; to: string }[],
    addedRelationships: [] as { source: string; target: string }[],
    removedRelationships: [] as string[],
  }

  for (const change of suggestion.changes) {
    switch (change.action) {
      case 'remove_table':
        if (change.table) result.removedTables.push(change.table)
        break
      case 'add_table':
        if (change.table) result.addedTables.push(change.table)
        break
      case 'merge_table':
        if (change.source_table) result.removedTables.push(change.source_table)
        if (change.target_table) result.modifiedTables.push(change.target_table)
        break
      case 'add_column':
        if (change.table && change.column) result.addedColumns.push({ table: change.table, column: change.column })
        break
      case 'remove_column':
        if (change.table && change.column) result.removedColumns.push({ table: change.table, column: change.column })
        break
      case 'move_column':
        if (change.column && change.from_table && change.to_table)
          result.movedColumns.push({ column: change.column, from: change.from_table, to: change.to_table })
        break
      case 'add_relationship':
        if (change.source_table && change.target_table)
          result.addedRelationships.push({ source: change.source_table, target: change.target_table })
        break
      case 'remove_relationship':
        if (change.constraint_name) result.removedRelationships.push(change.constraint_name)
        break
    }
  }

  return result
}
