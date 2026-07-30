// frontend/src/types/schema.ts

export interface Column {
  name: string
  data_type: string  // Simplified type (varchar, not varchar(255))
  is_nullable: boolean
  is_primary_key: boolean
  is_identity: boolean
  description?: string  // AI-generated plain-English description
}

export interface ForeignKey {
  constraint_name: string
  source_table: string
  source_schema: string
  source_columns: string[]  // Supports composite FKs
  target_table: string
  target_schema: string
  target_columns: string[]
}

export interface Index {
  name: string
  index_type: string  // CLUSTERED, NONCLUSTERED
  is_unique: boolean
  columns: string[]
  included_columns: string[]
}

export interface Table {
  object_id: number  // SQL Server internal ID
  schema_name: string
  table_name: string
  columns: Column[]
  indexes: Index[]
  is_view: boolean   // True for views, false for base tables
  description?: string  // AI-generated plain-English description
}

export interface DatabaseSchema {
  database_name: string
  tables: Table[]
  foreign_keys: ForeignKey[]
  extraction_time_seconds: number
  table_count: number
  standalone_table_count: number
  dataset_order?: Record<string, number> // schema_name → addition order (1 = first added)
  dataset_sources?: Record<string, 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'> // schema_name → source type
}

export interface ExtractionProgress {
  percentage: number  // 0-100
  current_table: string | null
  message: string
  status: 'progress' | 'complete' | 'error' | 'warning'
}

export interface StartExtractionResponse {
  stream_id: string
  table_count: number
  requires_confirmation: boolean
  message?: string  // For empty DB or errors
}

export interface DatabaseInfo {
  name: string
  table_count: number
}
