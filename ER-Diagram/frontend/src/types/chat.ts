// Chat types for the AI Schema Advisor

export interface ClarificationOption {
  id: string
  label: string
}

export interface ClarificationQuestion {
  id: string
  text: string
  options: ClarificationOption[]
  allow_custom_input: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  suggestions?: Suggestion[]
  clarifications?: ClarificationQuestion[]
  queryPlan?: QueryStep[]
  queryResults?: QueryResults
  planDescription?: string             // Planning explanation (shown in workflow)
  liveWorkflowSteps?: WorkflowStep[]  // Real-time steps before final result
  isStreaming?: boolean
}

export interface SchemaChange {
  action:
    | 'add_table'
    | 'remove_table'
    | 'merge_table'
    | 'add_column'
    | 'remove_column'
    | 'move_column'
    | 'add_relationship'
    | 'remove_relationship'
  table?: string
  schema_name?: string
  source_table?: string
  target_table?: string
  column?: string
  data_type?: string
  is_nullable?: boolean
  from_table?: string
  to_table?: string
  source_schema?: string
  target_schema?: string
  source_columns?: string[]
  target_columns?: string[]
  constraint_name?: string
  columns?: { name: string; data_type: string; is_nullable: boolean }[]
}

export interface Suggestion {
  id: string
  title: string
  changes: SchemaChange[]
  status?: 'pending' | 'accepted' | 'skipped'
}

export interface QueryStep {
  source: 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'
  query: string
  alias: string
  dataset?: string
}

export interface QuerySourceResult {
  alias: string
  columns?: string[]
  rows?: (string | number | boolean | null)[][]
  row_count?: number
  total_rows?: number
  truncated?: boolean
  bytes_processed?: number
  error?: string
}

export interface WorkflowStep {
  type: 'planning' | 'query' | 'merge' | 'summarizing'
  status: 'success' | 'error' | 'running' | 'retrying' | 'fixing'
  source?: 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'
  alias?: string
  query?: string
  description?: string
  rows?: number
  time?: number
  bytes_processed?: number
  error?: string
}

export interface Workflow {
  steps: WorkflowStep[]
  total_time: number
}

export interface QueryResults {
  sources: QuerySourceResult[]
  merged?: QuerySourceResult
  workflow?: Workflow
}

export interface DataSource {
  type: 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse'
  project_id?: string
  access_token?: string
  host?: string
  port?: number
  database?: string
  username?: string
  password?: string
  environment_url?: string
}

export interface ChatRequest {
  message: string
  schema: import('./schema').DatabaseSchema
  history: { role: 'user' | 'assistant'; content: string }[]
  data_sources: DataSource[]
}
