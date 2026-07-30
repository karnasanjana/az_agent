'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { StepIndicator } from '@/components/step-indicator'
import {
  startExtraction,
  confirmExtraction,
  fetchExtractedSchema,
  startBigQueryExtraction,
  fetchBigQuerySchema,
  startDataverseExtraction,
  fetchDataverseSchema,
  startPostgresExtraction,
  fetchPostgresSchema,
} from '@/app/actions'
import type { DatabaseSchema, StartExtractionResponse } from '@/types/schema'

type PageState = 'initial' | 'warning' | 'extracting' | 'complete' | 'error'
type DbType = 'sqlserver' | 'postgres' | 'bigquery' | 'dataverse'

interface SqlServerCredentials {
  host: string
  port: number
  database: string
  username: string
  password: string
}

export default function ExtractPage() {
  const router = useRouter()
  const [state, setState] = useState<PageState>('initial')
  const [dbType, setDbType] = useState<DbType>('sqlserver')
  const [credentials, setCredentials] = useState<SqlServerCredentials | null>(null)
  const [selectedDatabases, setSelectedDatabases] = useState<string[]>([])
  const [bqProjectId, setBqProjectId] = useState<string | null>(null)
  const [bqAccessToken, setBqAccessToken] = useState<string | null>(null)
  const [dvEnvironmentUrl, setDvEnvironmentUrl] = useState<string | null>(null)
  const [dvAccessToken, setDvAccessToken] = useState<string | null>(null)
  const [streamId, setStreamId] = useState<string | null>(null)
  const [tableCount, setTableCount] = useState<number>(0)
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Load state from sessionStorage on mount
  useEffect(() => {
    const storedDbType = sessionStorage.getItem('db_type') as DbType | null
    if (storedDbType) {
      setDbType(storedDbType)
    }

    const storedDatabases = sessionStorage.getItem('selected_databases')
    if (storedDatabases) {
      try {
        setSelectedDatabases(JSON.parse(storedDatabases))
      } catch {
        // Invalid stored data
      }
    }

    if (storedDbType === 'bigquery') {
      const projectId = sessionStorage.getItem('bq_project_id')
      const accessToken = sessionStorage.getItem('bq_access_token')
      setBqProjectId(projectId)
      setBqAccessToken(accessToken)
    } else if (storedDbType === 'dataverse') {
      const envUrl = sessionStorage.getItem('dv_environment_url')
      const token = sessionStorage.getItem('dv_access_token')
      setDvEnvironmentUrl(envUrl)
      setDvAccessToken(token)
    } else {
      const stored = sessionStorage.getItem('db_credentials')
      if (stored) {
        try {
          setCredentials(JSON.parse(stored))
        } catch {
          // Invalid stored credentials
        }
      }
    }
  }, [])

  const handleStartExtraction = async () => {
    if (dbType === 'bigquery') {
      await handleBigQueryExtraction()
    } else if (dbType === 'dataverse') {
      await handleDataverseExtraction()
    } else if (dbType === 'postgres') {
      await handlePostgresExtraction()
    } else {
      await handleSqlServerExtraction()
    }
  }

  const handlePostgresExtraction = async () => {
    if (!credentials) { setError('No PostgreSQL credentials found. Please connect first.'); setState('error'); return }
    setLoading(true); setError(null)
    try {
      const response = await startPostgresExtraction(credentials)
      if (response.table_count === 0) { setError('No tables found in this PostgreSQL database.'); setState('error'); return }
      setStreamId(response.stream_id); setTableCount(response.table_count); setState('extracting')
      const result = await fetchPostgresSchema(response.stream_id)
      if (!result.schemaJson) { setError(result.error || 'Failed to extract PostgreSQL schema'); setState('error'); return }
      const schemaData: DatabaseSchema = JSON.parse(result.schemaJson)
      const sources: Record<string, 'postgres'> = {}
      Array.from(new Set(schemaData.tables.map((t) => t.schema_name))).forEach((name) => { sources[name] = 'postgres' })
      schemaData.dataset_sources = sources
      sessionStorage.setItem('extracted_schema', JSON.stringify(schemaData))
      sessionStorage.removeItem('current_diagram_id'); sessionStorage.removeItem('current_diagram_name')
      setSchema(schemaData); setState('complete')
    } catch (err) { setError(err instanceof Error ? err.message : 'PostgreSQL extraction failed'); setState('error') }
    finally { setLoading(false) }
  }

  const handleSqlServerExtraction = async () => {
    if (!credentials) {
      setError('No database credentials found. Please connect first.')
      setState('error')
      return
    }

    setLoading(true)
    setError(null)

    try {
      // Extract each selected database (or the default one from credentials)
      const databasesToExtract = selectedDatabases.length > 0
        ? selectedDatabases
        : [credentials.database]

      // For now, extract the first database (multi-database merging can be added later)
      for (const dbName of databasesToExtract) {
        const creds = { ...credentials, database: dbName }
        const response: StartExtractionResponse = await startExtraction(creds)

        if (response.table_count === 0) {
          setError(`No tables found in ${dbName}. This database appears empty.`)
          setState('error')
          setLoading(false)
          return
        }

        setStreamId(response.stream_id)
        setTableCount(response.table_count)

        if (response.requires_confirmation) {
          setState('warning')
          setLoading(false)
          return
        }

        setState('extracting')
        const result = await fetchExtractedSchema(response.stream_id)
        if (result.schemaJson) {
          const schemaData: DatabaseSchema = typeof result.schemaJson === 'string'
            ? JSON.parse(result.schemaJson)
            : result.schemaJson as unknown as DatabaseSchema
          // Tag all datasets in this schema as SQL Server
          const dsNames = Array.from(new Set(schemaData.tables.map((t) => t.schema_name)))
          const sources: Record<string, 'bigquery' | 'sqlserver'> = {}
          dsNames.forEach((ds) => { sources[ds] = 'sqlserver' })
          schemaData.dataset_sources = sources
          sessionStorage.setItem('extracted_schema', JSON.stringify(schemaData))
          // Clear any previous diagram tracking (this is a fresh extraction)
          sessionStorage.removeItem('current_diagram_id')
          sessionStorage.removeItem('current_diagram_name')
          setSchema(schemaData)
          setState('complete')
        } else {
          setError(result.error || 'Failed to extract schema')
          setState('error')
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start extraction')
      setState('error')
    } finally {
      setLoading(false)
    }
  }

  const handleBigQueryExtraction = async () => {
    if (!bqProjectId || !bqAccessToken) {
      setError('BigQuery credentials not found. Please connect first.')
      setState('error')
      return
    }

    if (selectedDatabases.length === 0) {
      setError('No datasets selected. Please go back and select datasets.')
      setState('error')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await startBigQueryExtraction(
        bqProjectId,
        bqAccessToken,
        selectedDatabases
      )

      if (response.table_count === 0) {
        setError('No tables found in the selected datasets.')
        setState('error')
        setLoading(false)
        return
      }

      setStreamId(response.stream_id)
      setTableCount(response.table_count)

      if (response.requires_confirmation) {
        setState('warning')
        setLoading(false)
        return
      }

      setState('extracting')
      const result = await fetchBigQuerySchema(response.stream_id)
      if (result.schemaJson) {
        const schemaData: DatabaseSchema = typeof result.schemaJson === 'string'
          ? JSON.parse(result.schemaJson)
          : result.schemaJson as unknown as DatabaseSchema
        // Tag all datasets in this schema as BigQuery
        const dsNames = Array.from(new Set(schemaData.tables.map((t) => t.schema_name)))
        const sources: Record<string, 'bigquery' | 'sqlserver'> = {}
        dsNames.forEach((ds) => { sources[ds] = 'bigquery' })
        schemaData.dataset_sources = sources
        sessionStorage.setItem('extracted_schema', JSON.stringify(schemaData))
        setSchema(schemaData)
        setState('complete')
      } else {
        setError(result.error || 'Failed to extract schema')
        setState('error')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start extraction')
      setState('error')
    } finally {
      setLoading(false)
    }
  }

  const handleDataverseExtraction = async () => {
    if (!dvEnvironmentUrl || !dvAccessToken) {
      setError('Dataverse credentials not found. Please connect first.')
      setState('error')
      return
    }

    if (selectedDatabases.length === 0) {
      setError('No entities selected. Please go back and select entities.')
      setState('error')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await startDataverseExtraction(
        dvEnvironmentUrl,
        dvAccessToken,
        selectedDatabases
      )

      if (response.table_count === 0) {
        setError('No tables found in the selected entities.')
        setState('error')
        setLoading(false)
        return
      }

      setStreamId(response.stream_id)
      setTableCount(response.table_count)

      if (response.requires_confirmation) {
        setState('warning')
        setLoading(false)
        return
      }

      setState('extracting')
      const result = await fetchDataverseSchema(response.stream_id)
      if (result.schemaJson) {
        const schemaData: DatabaseSchema = typeof result.schemaJson === 'string'
          ? JSON.parse(result.schemaJson)
          : result.schemaJson as unknown as DatabaseSchema
        // Tag all datasets in this schema as Dataverse
        const dsNames = Array.from(new Set(schemaData.tables.map((t) => t.schema_name)))
        const sources: Record<string, 'bigquery' | 'sqlserver' | 'dataverse'> = {}
        dsNames.forEach((ds) => { sources[ds] = 'dataverse' })
        schemaData.dataset_sources = sources as Record<string, 'bigquery' | 'sqlserver'>
        sessionStorage.setItem('extracted_schema', JSON.stringify(schemaData))
        sessionStorage.removeItem('current_diagram_id')
        sessionStorage.removeItem('current_diagram_name')
        setSchema(schemaData)
        setState('complete')
      } else {
        setError(result.error || 'Failed to extract schema')
        setState('error')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start extraction')
      setState('error')
    } finally {
      setLoading(false)
    }
  }

  const handleConfirm = async () => {
    if (!streamId) return

    setLoading(true)
    try {
      await confirmExtraction(streamId)
      setState('extracting')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to confirm extraction')
      setState('error')
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => {
    setStreamId(null)
    setTableCount(0)
    setState('initial')
  }

  const handleRetry = () => {
    setError(null)
    setStreamId(null)
    setSchema(null)
    setState('initial')
  }

  const sourceLabel = dbType === 'bigquery' ? 'BigQuery' : dbType === 'dataverse' ? 'Dataverse' : dbType === 'postgres' ? 'PostgreSQL' : 'SQL Server'
  const itemLabel = dbType === 'bigquery' ? 'datasets' : dbType === 'dataverse' ? 'entities' : 'databases'

  return (
    <main className="min-h-screen bg-gradient-surface py-12">
      <div className="container mx-auto px-4 max-w-2xl">
        <StepIndicator currentStep={2} />
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-slate-100">Schema Extraction</h1>
          <p className="mt-2 text-slate-400">
            Extract your database schema for ER diagram generation
          </p>
        </div>

        {/* Initial State - Start Button */}
        {state === 'initial' && (
          <div className="text-center">
            {(credentials || (bqProjectId && bqAccessToken) || (dvEnvironmentUrl && dvAccessToken)) ? (
              <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-6">
                <div className="mb-4">
                  <span className="inline-block px-2.5 py-1 text-xs font-medium bg-indigo-500/20 text-indigo-300 rounded-full border border-indigo-500/30 mb-2">
                    {sourceLabel}
                  </span>
                  {(dbType === 'sqlserver' || dbType === 'postgres') && credentials && (
                    <p className="text-slate-300">
                      Server: <span className="font-medium text-slate-100">{credentials.host}</span>
                    </p>
                  )}
                  {dbType === 'bigquery' && bqProjectId && (
                    <p className="text-slate-300">
                      Project: <span className="font-medium text-slate-100">{bqProjectId}</span>
                    </p>
                  )}
                  {dbType === 'dataverse' && dvEnvironmentUrl && (
                    <p className="text-slate-300">
                      Environment: <span className="font-medium text-slate-100">{dvEnvironmentUrl}</span>
                    </p>
                  )}
                  {selectedDatabases.length > 0 && (
                    <div className="mt-2">
                      <p className="text-sm text-slate-500 mb-1">
                        Selected {itemLabel}: {selectedDatabases.length}
                      </p>
                      <div className="flex flex-wrap gap-1 justify-center">
                        {selectedDatabases.map((db) => (
                          <span
                            key={db}
                            className="inline-block px-2 py-0.5 text-xs bg-slate-800 text-slate-300 rounded border border-slate-700"
                          >
                            {db}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <button
                  onClick={handleStartExtraction}
                  disabled={loading}
                  className="px-6 py-3 bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 transition-colors font-medium shadow-[0_0_15px_rgba(79,70,229,0.4)]"
                >
                  {loading ? 'Starting...' : 'Start Extraction'}
                </button>
              </div>
            ) : (
              <div className="bg-amber-900/30 text-amber-300 border border-amber-500/30 p-4 rounded-xl">
                <p className="mb-2 font-medium">No database connection found</p>
                <p className="text-amber-400/80">
                  Please connect to your database first to extract its schema.
                </p>
                <a href="/" className="mt-2 inline-block underline font-medium hover:text-amber-200">
                  Go to Connection Page
                </a>
              </div>
            )}
          </div>
        )}

        {/* Warning State - Large Database Confirmation */}
        {state === 'warning' && (
          <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-6">
            <div className="text-center">
              <div className="mx-auto w-12 h-12 rounded-full bg-amber-900/50 flex items-center justify-center mb-4 border border-amber-500/30">
                <svg
                  className="w-6 h-6 text-amber-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-slate-100 mb-2">
                Large {sourceLabel} Detected
              </h2>
              <p className="text-slate-400 mb-6">
                This extraction covers <span className="font-bold text-slate-200">{tableCount}</span> tables.
                It may take a while. Continue?
              </p>
              <div className="flex justify-center gap-4">
                <button
                  onClick={handleCancel}
                  disabled={loading}
                  className="px-6 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={loading}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 disabled:bg-slate-700 transition-colors"
                >
                  {loading ? 'Confirming...' : 'Continue'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Extracting State - Loading indicator */}
        {state === 'extracting' && (
          <div className="w-full max-w-md mx-auto p-6 glass-panel bg-slate-900/60 rounded-2xl border border-slate-700">
            <div className="text-center">
              <div className="animate-spin rounded-full h-10 w-10 border-2 border-indigo-500 border-t-transparent mx-auto mb-4"></div>
              <p className="text-slate-200 font-medium">Extracting schema...</p>
              <p className="text-sm text-slate-500 mt-2">
                {dbType === 'bigquery'
                  ? 'Connecting to BigQuery and reading table structures'
                  : dbType === 'dataverse'
                  ? 'Connecting to Dataverse and reading entity structures'
                  : 'Connecting to database and reading table structures'}
              </p>
              {selectedDatabases.length > 0 && (
                <p className="text-xs text-slate-600 mt-1">
                  {selectedDatabases.length} {itemLabel} selected
                </p>
              )}
            </div>
          </div>
        )}

        {/* Complete State - Results Summary */}
        {state === 'complete' && schema && (
          <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-6">
            <div className="text-center">
              <div className="mx-auto w-12 h-12 rounded-full bg-emerald-900/50 flex items-center justify-center mb-4 border border-emerald-500/30">
                <svg
                  className="w-6 h-6 text-emerald-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-slate-100 mb-2">
                Extraction Complete!
              </h2>
              <div className="text-slate-400 mb-6 space-y-1">
                <p>
                  <span className="font-bold text-slate-200">{schema.table_count}</span> tables extracted
                  {dbType === 'bigquery' && ' from BigQuery'}
                </p>
                <p>
                  <span className="font-bold text-slate-200">{schema.foreign_keys?.length ?? 0}</span> foreign key
                  relationships
                </p>
                <p className="text-sm text-slate-500">
                  Completed in {schema.extraction_time_seconds?.toFixed(2) ?? '0'} seconds
                </p>
              </div>
              <div className="flex justify-center gap-4">
                <button
                  onClick={handleRetry}
                  className="px-6 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-800 transition-colors"
                >
                  Extract Again
                </button>
                <button
                  onClick={() => router.push('/diagram')}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition-colors font-medium shadow-[0_0_15px_rgba(79,70,229,0.4)]"
                >
                  Next: View Diagram →
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Error State */}
        {state === 'error' && (
          <div className="glass-panel bg-slate-900/60 rounded-2xl border border-slate-700 p-6">
            <div className="text-center">
              <div className="mx-auto w-12 h-12 rounded-full bg-red-900/50 flex items-center justify-center mb-4 border border-red-500/30">
                <svg
                  className="w-6 h-6 text-red-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-slate-100 mb-2">
                Extraction Failed
              </h2>
              <p className="text-red-400 mb-6">{error || 'An unexpected error occurred'}</p>
              <div className="flex justify-center gap-4">
                <a
                  href="/"
                  className="px-6 py-2 border border-slate-600 text-slate-300 rounded-lg hover:bg-slate-800 transition-colors"
                >
                  Start Over
                </a>
                <button
                  onClick={handleRetry}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition-colors"
                >
                  Try Again
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
