'use client'

import { useState, useCallback, useRef } from 'react'
import { useSession } from 'next-auth/react'
import { PublicClientApplication, type AuthenticationResult } from '@azure/msal-browser'
import {
  listBigQueryDatasets,
  listSqlServerDatabases,
  startBigQueryExtraction,
  fetchBigQuerySchema,
  startExtraction,
  fetchExtractedSchema,
  listDataverseEntities,
  startDataverseExtraction,
  fetchDataverseSchema,
} from '@/app/actions'
import { getCacheKey, getCachedSchema, setCachedSchema } from '@/lib/schema-cache'
import type { DatabaseSchema, DatabaseInfo } from '@/types/schema'

interface AddDataSourceModalProps {
  isOpen: boolean
  onClose: () => void
  loadedDatasets: string[] // Already loaded dataset/database names (schema_name values)
  onAdd: (schema: DatabaseSchema, sourceType: 'bigquery' | 'sqlserver' | 'postgres' | 'dataverse') => void
}

type Tab = 'bigquery' | 'sqlserver' | 'dataverse'
type ModalState = 'idle' | 'connecting' | 'ready' | 'extracting' | 'error'

/**
 * Modal for adding data sources (BigQuery or SQL Server) to the diagram.
 * Supports schema caching via localStorage with 10-minute TTL.
 */
export function AddDataSourceModal({
  isOpen,
  onClose,
  loadedDatasets,
  onAdd,
}: AddDataSourceModalProps) {
  const { data: session } = useSession()
  const accessToken = (session as any)?.accessToken as string | undefined

  const [activeTab, setActiveTab] = useState<Tab>('bigquery')

  // BigQuery state
  const [bqProjectId, setBqProjectId] = useState('')
  const [bqDatasets, setBqDatasets] = useState<DatabaseInfo[]>([])
  const [bqSelected, setBqSelected] = useState<string[]>([])

  // SQL Server state
  const [sqlHost, setSqlHost] = useState('')
  const [sqlPort, setSqlPort] = useState('1433')
  const [sqlUsername, setSqlUsername] = useState('')
  const [sqlPassword, setSqlPassword] = useState('')
  const [sqlDatabases, setSqlDatabases] = useState<DatabaseInfo[]>([])
  const [sqlSelected, setSqlSelected] = useState<string[]>([])

  // Dataverse state
  const [dvEnvironmentUrl, setDvEnvironmentUrl] = useState('')
  const [dvEntities, setDvEntities] = useState<DatabaseInfo[]>([])
  const [dvSelected, setDvSelected] = useState<string[]>([])
  const [dvSignedIn, setDvSignedIn] = useState(false)
  const [dvAccessToken, setDvAccessToken] = useState<string | null>(null)
  const [dvSearch, setDvSearch] = useState('')

  // Shared state
  const [state, setState] = useState<ModalState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [extractionMessage, setExtractionMessage] = useState<string>('')

  const resetState = useCallback(() => {
    setState('idle')
    setError(null)
    setExtractionMessage('')
  }, [])

  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab)
    resetState()
  }, [resetState])

  // --- MSAL singleton for Dataverse ---
  const msalRef = useRef<PublicClientApplication | null>(null)
  const msalInitPromiseRef = useRef<Promise<void> | null>(null)

  const getMsalInstance = useCallback(async (): Promise<PublicClientApplication> => {
    if (!msalRef.current) {
      msalRef.current = new PublicClientApplication({
        auth: {
          clientId: '2967332b-4aa0-4a9a-89ca-596d6d54a009',
          authority: 'https://login.microsoftonline.com/common',
          redirectUri: window.location.origin,
        },
        cache: { cacheLocation: 'sessionStorage' },
      })
      msalInitPromiseRef.current = msalRef.current.initialize()
    }
    await msalInitPromiseRef.current
    return msalRef.current
  }, [])

  // --- BigQuery ---

  const handleFetchDatasets = async () => {
    if (!bqProjectId.trim()) return
    setState('connecting')
    setError(null)
    setBqDatasets([])
    setBqSelected([])

    try {
      if (!accessToken) {
        setError('Google sign-in required. Please sign in to access BigQuery.')
        setState('error')
        return
      }
      const { datasets, error: err } = await listBigQueryDatasets(bqProjectId.trim(), accessToken)
      if (err || !datasets) {
        setError(err || 'Failed to fetch datasets')
        setState('error')
        return
      }
      setBqDatasets(datasets)
      // Store BigQuery credentials so chat page can query BigQuery
      sessionStorage.setItem('bq_project_id', bqProjectId.trim())
      sessionStorage.setItem('bq_access_token', accessToken)
      setState('ready')
    } catch {
      setError('Failed to connect to BigQuery. Please check the project ID.')
      setState('error')
    }
  }

  const handleAddBigQuery = async () => {
    const newSelected = bqSelected.filter(d => !loadedDatasets.includes(d))
    if (newSelected.length === 0) return

    setState('extracting')
    setError(null)

    try {
      // Check cache for each selected dataset
      const cachedSchemas: DatabaseSchema[] = []
      const uncachedDatasets: string[] = []

      for (const ds of newSelected) {
        const key = getCacheKey('bigquery', bqProjectId.trim(), ds)
        const cached = getCachedSchema(key)
        if (cached) {
          cachedSchemas.push(cached)
        } else {
          uncachedDatasets.push(ds)
        }
      }

      if (cachedSchemas.length > 0 && uncachedDatasets.length === 0) {
        setExtractionMessage('Extracting schema... (from cache)')
      } else if (cachedSchemas.length > 0) {
        setExtractionMessage(`Extracting schema... (${cachedSchemas.length} from cache)`)
      } else {
        setExtractionMessage('Extracting schema...')
      }

      // Extract uncached datasets if any
      let freshSchema: DatabaseSchema | null = null
      if (uncachedDatasets.length > 0) {
        if (!accessToken) {
          setError('Google sign-in required. Please sign in to access BigQuery.')
          setState('ready')
          return
        }
        const { stream_id } = await startBigQueryExtraction(
          bqProjectId.trim(),
          accessToken,
          uncachedDatasets
        )
        const { schemaJson, error: extractError } = await fetchBigQuerySchema(stream_id)
        if (extractError || !schemaJson) {
          setError(extractError || 'No schema data received')
          setState('ready')
          return
        }
        freshSchema = JSON.parse(schemaJson)

        // Cache each dataset separately from the fresh extraction
        if (freshSchema) {
          for (const ds of uncachedDatasets) {
            const dsSchema: DatabaseSchema = {
              ...freshSchema,
              tables: freshSchema.tables.filter(t => t.schema_name === ds),
              foreign_keys: freshSchema.foreign_keys.filter(
                fk => fk.source_schema === ds || fk.target_schema === ds
              ),
              table_count: freshSchema.tables.filter(t => t.schema_name === ds).length,
            }
            const key = getCacheKey('bigquery', bqProjectId.trim(), ds)
            setCachedSchema(key, dsSchema)
          }
        }
      }

      // Merge all schemas (cached + fresh) and pass to onAdd
      const allSchemas = [...cachedSchemas]
      if (freshSchema) allSchemas.push(freshSchema)

      // Merge into a single schema
      const merged = mergeSchemas(allSchemas)
      if (merged) {
        onAdd(merged, 'bigquery')
      }
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
      setState('ready')
    }
  }

  // --- SQL Server ---

  const handleConnectSql = async () => {
    if (!sqlHost.trim() || !sqlUsername.trim() || !sqlPassword.trim()) return
    setState('connecting')
    setError(null)
    setSqlDatabases([])
    setSqlSelected([])

    try {
      const { databases, error: err } = await listSqlServerDatabases({
        host: sqlHost.trim(),
        port: parseInt(sqlPort, 10) || 1433,
        username: sqlUsername.trim(),
        password: sqlPassword,
      })
      if (err || !databases) {
        setError(err || 'Failed to list databases')
        setState('error')
        return
      }
      setSqlDatabases(databases)
      // Store SQL Server credentials so chat page can query SQL Server
      sessionStorage.setItem('db_credentials', JSON.stringify({
        host: sqlHost.trim(),
        port: parseInt(sqlPort, 10) || 1433,
        username: sqlUsername.trim(),
        password: sqlPassword,
      }))
      setState('ready')
    } catch {
      setError('Failed to connect to SQL Server.')
      setState('error')
    }
  }

  const handleAddSqlServer = async () => {
    const newSelected = sqlSelected.filter(d => !loadedDatasets.includes(d))
    if (newSelected.length === 0) return

    setState('extracting')
    setError(null)

    try {
      const host = sqlHost.trim()
      const port = parseInt(sqlPort, 10) || 1433
      const username = sqlUsername.trim()
      const password = sqlPassword

      const cachedSchemas: DatabaseSchema[] = []
      const uncachedDatabases: string[] = []

      for (const db of newSelected) {
        const key = getCacheKey('sqlserver', host, db)
        const cached = getCachedSchema(key)
        if (cached) {
          cachedSchemas.push(cached)
        } else {
          uncachedDatabases.push(db)
        }
      }

      if (cachedSchemas.length > 0 && uncachedDatabases.length === 0) {
        setExtractionMessage('Extracting schema... (from cache)')
      } else if (cachedSchemas.length > 0) {
        setExtractionMessage(`Extracting schema... (${cachedSchemas.length} from cache)`)
      } else {
        setExtractionMessage('Extracting schema...')
      }

      // Update stored credentials with selected database for chat queries
      sessionStorage.setItem('db_credentials', JSON.stringify({
        host, port, database: newSelected[0], username, password,
      }))

      // Extract each uncached database separately
      const freshSchemas: DatabaseSchema[] = []
      for (const db of uncachedDatabases) {
        setExtractionMessage(`Extracting ${db}...`)
        const { stream_id } = await startExtraction({
          host,
          port,
          database: db,
          username,
          password,
        })
        const { schemaJson, error: extractError } = await fetchExtractedSchema(stream_id)
        if (extractError || !schemaJson) {
          setError(extractError || `No schema data received for ${db}`)
          setState('ready')
          return
        }
        const schema: DatabaseSchema = JSON.parse(schemaJson)
        freshSchemas.push(schema)

        // Cache the extracted schema
        const key = getCacheKey('sqlserver', host, db)
        setCachedSchema(key, schema)
      }

      // Merge all schemas
      const allSchemas = [...cachedSchemas, ...freshSchemas]
      const merged = mergeSchemas(allSchemas)
      if (merged) {
        onAdd(merged, 'sqlserver')
      }
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
      setState('ready')
    }
  }

  // --- Dataverse ---

  const handleConnectDataverse = async () => {
    const envUrl = dvEnvironmentUrl.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
    if (!envUrl) return

    setState('connecting')
    setError(null)
    setDvEntities([])
    setDvSelected([])

    try {
      const msalInstance = await getMsalInstance()
      const scopes = [`https://${envUrl}/user_impersonation`]
      let token: string

      // Try silent token acquisition first (user may already be signed in)
      const accounts = msalInstance.getAllAccounts()
      if (accounts.length > 0) {
        try {
          const silentResult = await msalInstance.acquireTokenSilent({
            scopes,
            account: accounts[0],
          })
          token = silentResult.accessToken
        } catch {
          // Silent failed — check sessionStorage for previously saved token
          const savedToken = sessionStorage.getItem('dv_access_token')
          if (savedToken) {
            token = savedToken
          } else {
            // Last resort: try popup
            const result: AuthenticationResult = await msalInstance.loginPopup({ scopes })
            token = result.accessToken
          }
        }
      } else {
        // No cached accounts — check sessionStorage from home page auth
        const savedToken = sessionStorage.getItem('dv_access_token')
        if (savedToken) {
          token = savedToken
        } else {
          // No saved token — must use popup
          const result: AuthenticationResult = await msalInstance.loginPopup({ scopes })
          token = result.accessToken
        }
      }

      setDvAccessToken(token)
      setDvSignedIn(true)

      const { entities, error: err } = await listDataverseEntities(envUrl, token)
      if (err || !entities) {
        setError(err || 'Failed to fetch entities')
        setState('error')
        return
      }
      setDvEntities(entities)
      sessionStorage.setItem('dv_environment_url', envUrl)
      sessionStorage.setItem('dv_access_token', token)
      setState('ready')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Authentication failed'
      if (message.includes('user_cancelled') || message.includes('User cancelled')) {
        setError('Sign-in was cancelled.')
      } else {
        setError(`Microsoft sign-in failed: ${message}`)
      }
      setState('error')
    }
  }

  const handleAddDataverse = async () => {
    const newSelected = dvSelected.filter(d => !loadedDatasets.includes(d))
    if (newSelected.length === 0) return

    setState('extracting')
    setError(null)

    try {
      const envUrl = dvEnvironmentUrl.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')

      const cachedSchemas: DatabaseSchema[] = []
      const uncachedEntities: string[] = []

      for (const entity of newSelected) {
        const key = getCacheKey('dataverse', envUrl, entity)
        const cached = getCachedSchema(key)
        if (cached) {
          cachedSchemas.push(cached)
        } else {
          uncachedEntities.push(entity)
        }
      }

      if (cachedSchemas.length > 0 && uncachedEntities.length === 0) {
        setExtractionMessage('Extracting schema... (from cache)')
      } else if (cachedSchemas.length > 0) {
        setExtractionMessage(`Extracting schema... (${cachedSchemas.length} from cache)`)
      } else {
        setExtractionMessage('Extracting schema...')
      }

      let freshSchema: DatabaseSchema | null = null
      if (uncachedEntities.length > 0) {
        if (!dvAccessToken) {
          setError('Microsoft sign-in required.')
          setState('ready')
          return
        }
        const { stream_id } = await startDataverseExtraction(
          envUrl,
          dvAccessToken,
          uncachedEntities
        )
        const { schemaJson, error: extractError } = await fetchDataverseSchema(stream_id)
        if (extractError || !schemaJson) {
          setError(extractError || 'No schema data received')
          setState('ready')
          return
        }
        freshSchema = JSON.parse(schemaJson)

        if (freshSchema) {
          for (const entity of uncachedEntities) {
            const dsSchema: DatabaseSchema = {
              ...freshSchema,
              tables: freshSchema.tables.filter(t => t.schema_name === entity),
              foreign_keys: freshSchema.foreign_keys.filter(
                fk => fk.source_schema === entity || fk.target_schema === entity
              ),
              table_count: freshSchema.tables.filter(t => t.schema_name === entity).length,
            }
            const key = getCacheKey('dataverse', envUrl, entity)
            setCachedSchema(key, dsSchema)
          }
        }
      }

      const allSchemas = [...cachedSchemas]
      if (freshSchema) allSchemas.push(freshSchema)

      const merged = mergeSchemas(allSchemas)
      if (merged) {
        onAdd(merged, 'dataverse')
      }
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed')
      setState('ready')
    }
  }

  // --- Helpers ---

  const toggleItem = (name: string, list: string[], setList: (v: string[]) => void) => {
    if (loadedDatasets.includes(name)) return
    setList(
      list.includes(name) ? list.filter(d => d !== name) : [...list, name]
    )
  }

  if (!isOpen) return null

  const bqNewSelected = bqSelected.filter(d => !loadedDatasets.includes(d))
  const sqlNewSelected = sqlSelected.filter(d => !loadedDatasets.includes(d))
  const dvNewSelected = dvSelected.filter(d => !loadedDatasets.includes(d))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-shrink-0">
          <h2 className="text-lg font-bold text-gray-900">Add Data Source to Diagram</h2>
          <button
            onClick={onClose}
            disabled={state === 'extracting'}
            className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="px-6 pt-4 flex gap-2 flex-shrink-0">
          <button
            onClick={() => handleTabChange('bigquery')}
            disabled={state === 'extracting'}
            className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ${
              activeTab === 'bigquery'
                ? 'bg-blue-50 text-blue-700 border-2 border-blue-300'
                : 'bg-gray-50 text-gray-600 border-2 border-transparent hover:border-gray-200'
            } disabled:opacity-50`}
          >
            <span>BigQuery</span>
          </button>
          <button
            onClick={() => handleTabChange('sqlserver')}
            disabled={state === 'extracting'}
            className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ${
              activeTab === 'sqlserver'
                ? 'bg-blue-50 text-blue-700 border-2 border-blue-300'
                : 'bg-gray-50 text-gray-600 border-2 border-transparent hover:border-gray-200'
            } disabled:opacity-50`}
          >
            <span>SQL Server</span>
          </button>
          <button
            onClick={() => handleTabChange('dataverse')}
            disabled={state === 'extracting'}
            className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ${
              activeTab === 'dataverse'
                ? 'bg-blue-50 text-blue-700 border-2 border-blue-300'
                : 'bg-gray-50 text-gray-600 border-2 border-transparent hover:border-gray-200'
            } disabled:opacity-50`}
          >
            <span>Dataverse</span>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto flex-1">
          {/* Error banner */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* BigQuery Tab */}
          {activeTab === 'bigquery' && (
            <div className="space-y-4">
              {/* Project ID input */}
              <div>
                <label htmlFor="bq-project" className="block text-sm font-medium text-gray-700 mb-1">
                  Google Cloud Project ID
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    id="bq-project"
                    value={bqProjectId}
                    onChange={(e) => setBqProjectId(e.target.value)}
                    placeholder="my-gcp-project"
                    disabled={state === 'extracting'}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                  />
                  <button
                    onClick={handleFetchDatasets}
                    disabled={!bqProjectId.trim() || state === 'connecting' || state === 'extracting'}
                    className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors whitespace-nowrap"
                  >
                    {state === 'connecting' && activeTab === 'bigquery' ? 'Fetching...' : 'Fetch Datasets'}
                  </button>
                </div>
              </div>

              {/* Connecting spinner */}
              {state === 'connecting' && (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
                  <span className="text-gray-600 text-sm">Fetching datasets...</span>
                </div>
              )}

              {/* Dataset cards */}
              {(state === 'ready' || state === 'extracting' || (state === 'error' && bqDatasets.length > 0)) && bqDatasets.length > 0 && (
                <div className="grid grid-cols-2 gap-3">
                  {bqDatasets.map((ds) => {
                    const isLoaded = loadedDatasets.includes(ds.name)
                    const isSelected = bqSelected.includes(ds.name)
                    return (
                      <DataSourceCard
                        key={ds.name}
                        name={ds.name}
                        tableCount={ds.table_count}
                        isLoaded={isLoaded}
                        isSelected={isSelected}
                        disabled={state === 'extracting'}
                        onClick={() => toggleItem(ds.name, bqSelected, setBqSelected)}
                      />
                    )
                  })}
                </div>
              )}

              {state === 'ready' && bqDatasets.length === 0 && (
                <p className="text-gray-500 text-center py-8 text-sm">No datasets found in this project.</p>
              )}
            </div>
          )}

          {/* SQL Server Tab */}
          {activeTab === 'sqlserver' && (
            <div className="space-y-4">
              {/* Connection fields */}
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label htmlFor="sql-host" className="block text-sm font-medium text-gray-700 mb-1">
                    Host
                  </label>
                  <input
                    type="text"
                    id="sql-host"
                    value={sqlHost}
                    onChange={(e) => setSqlHost(e.target.value)}
                    placeholder="server.database.windows.net"
                    disabled={state === 'extracting'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                  />
                </div>
                <div>
                  <label htmlFor="sql-port" className="block text-sm font-medium text-gray-700 mb-1">
                    Port
                  </label>
                  <input
                    type="number"
                    id="sql-port"
                    value={sqlPort}
                    onChange={(e) => setSqlPort(e.target.value)}
                    placeholder="1433"
                    disabled={state === 'extracting'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                  />
                </div>
                <div>
                  <label htmlFor="sql-username" className="block text-sm font-medium text-gray-700 mb-1">
                    Username
                  </label>
                  <input
                    type="text"
                    id="sql-username"
                    value={sqlUsername}
                    onChange={(e) => setSqlUsername(e.target.value)}
                    placeholder="Username"
                    disabled={state === 'extracting'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                  />
                </div>
                <div className="col-span-2">
                  <label htmlFor="sql-password" className="block text-sm font-medium text-gray-700 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    id="sql-password"
                    value={sqlPassword}
                    onChange={(e) => setSqlPassword(e.target.value)}
                    placeholder="Password"
                    disabled={state === 'extracting'}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                  />
                </div>
              </div>

              <button
                onClick={handleConnectSql}
                disabled={!sqlHost.trim() || !sqlUsername.trim() || !sqlPassword.trim() || state === 'connecting' || state === 'extracting'}
                className="w-full py-2 px-4 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                {state === 'connecting' && activeTab === 'sqlserver' ? 'Connecting...' : 'Connect'}
              </button>

              {/* Connecting spinner */}
              {state === 'connecting' && (
                <div className="flex items-center justify-center py-4">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mr-2" />
                  <span className="text-gray-600 text-sm">Connecting to server...</span>
                </div>
              )}

              {/* Database cards */}
              {(state === 'ready' || state === 'extracting' || (state === 'error' && sqlDatabases.length > 0)) && sqlDatabases.length > 0 && (
                <>
                  <div className="pt-2">
                    <h3 className="text-sm font-medium text-gray-700 mb-2">Select databases</h3>
                    <div className="grid grid-cols-2 gap-3">
                      {sqlDatabases.map((db) => {
                        const isLoaded = loadedDatasets.includes(db.name)
                        const isSelected = sqlSelected.includes(db.name)
                        return (
                          <DataSourceCard
                            key={db.name}
                            name={db.name}
                            tableCount={db.table_count}
                            isLoaded={isLoaded}
                            isSelected={isSelected}
                            disabled={state === 'extracting'}
                            onClick={() => toggleItem(db.name, sqlSelected, setSqlSelected)}
                          />
                        )
                      })}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Dataverse Tab */}
          {activeTab === 'dataverse' && (
            <div className="space-y-4">
              {/* Environment URL input */}
              <div>
                <label htmlFor="dv-env-url" className="block text-sm font-medium text-gray-700 mb-1">
                  Environment URL
                </label>
                <input
                  type="text"
                  id="dv-env-url"
                  value={dvEnvironmentUrl}
                  onChange={(e) => setDvEnvironmentUrl(e.target.value)}
                  placeholder="org.crm.dynamics.com"
                  disabled={state === 'extracting'}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-gray-500">
                  e.g. yourorg.crm.dynamics.com (without https://)
                </p>
              </div>

              {!dvSignedIn ? (
                <button
                  onClick={handleConnectDataverse}
                  disabled={!dvEnvironmentUrl.trim() || state === 'connecting' || state === 'extracting'}
                  className="w-full py-2.5 px-4 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 transition-colors font-medium flex items-center justify-center gap-3 text-sm"
                >
                  {state === 'connecting' && activeTab === 'dataverse' ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600" />
                      Connecting...
                    </>
                  ) : (
                    <>
                      <svg className="w-4 h-4" viewBox="0 0 21 21">
                        <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                        <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                        <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                        <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                      </svg>
                      Connect with Microsoft
                    </>
                  )}
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <div className="flex-1 p-2 bg-green-50 border border-green-200 rounded-md">
                    <p className="text-xs text-green-700 flex items-center gap-1.5">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Signed in
                    </p>
                  </div>
                  <button
                    onClick={handleConnectDataverse}
                    disabled={state === 'extracting'}
                    className="px-3 py-2 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 transition-colors whitespace-nowrap"
                  >
                    Refresh
                  </button>
                </div>
              )}

              {/* Connecting spinner */}
              {state === 'connecting' && (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
                  <span className="text-gray-600 text-sm">Fetching entities...</span>
                </div>
              )}

              {/* Entity cards */}
              {(state === 'ready' || state === 'extracting' || (state === 'error' && dvEntities.length > 0)) && dvEntities.length > 0 && (
                <>
                  <div className="pt-2">
                    <h3 className="text-sm font-medium text-gray-700 mb-2">Select entities</h3>
                    {dvEntities.length > 6 && (
                      <input
                        type="text"
                        value={dvSearch}
                        onChange={(e) => setDvSearch(e.target.value)}
                        placeholder="Search entities..."
                        className="w-full mb-3 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    )}
                    <div className="grid grid-cols-2 gap-3">
                      {dvEntities.filter((e) => !dvSearch.trim() || e.name.toLowerCase().includes(dvSearch.toLowerCase())).map((entity) => {
                        const isLoaded = loadedDatasets.includes(entity.name)
                        const isSelected = dvSelected.includes(entity.name)
                        return (
                          <DataSourceCard
                            key={entity.name}
                            name={entity.name}
                            tableCount={entity.table_count}
                            isLoaded={isLoaded}
                            isSelected={isSelected}
                            disabled={state === 'extracting'}
                            onClick={() => toggleItem(entity.name, dvSelected, setDvSelected)}
                          />
                        )
                      })}
                    </div>
                  </div>
                </>
              )}

              {state === 'ready' && dvEntities.length === 0 && (
                <p className="text-gray-500 text-center py-8 text-sm">No entities found in this environment.</p>
              )}
            </div>
          )}

          {/* Extraction progress */}
          {state === 'extracting' && (
            <div className="flex items-center justify-center py-4 mt-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600 mr-2" />
              <span className="text-sm text-gray-600">{extractionMessage || 'Extracting schema...'}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-200 flex justify-between items-center flex-shrink-0">
          <span className="text-sm text-gray-500">
            {activeTab === 'bigquery'
              ? `${bqNewSelected.length} dataset${bqNewSelected.length !== 1 ? 's' : ''} selected`
              : activeTab === 'dataverse'
              ? `${dvNewSelected.length} entit${dvNewSelected.length !== 1 ? 'ies' : 'y'} selected`
              : `${sqlNewSelected.length} database${sqlNewSelected.length !== 1 ? 's' : ''} selected`}
          </span>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              disabled={state === 'extracting'}
              className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={activeTab === 'bigquery' ? handleAddBigQuery : activeTab === 'dataverse' ? handleAddDataverse : handleAddSqlServer}
              disabled={
                state === 'extracting' ||
                state === 'connecting' ||
                (activeTab === 'bigquery' ? bqNewSelected.length === 0 : activeTab === 'dataverse' ? dvNewSelected.length === 0 : sqlNewSelected.length === 0)
              }
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {state === 'extracting' ? 'Extracting...' : 'Add to Diagram'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Internal Components ---

function DataSourceCard({
  name,
  tableCount,
  isLoaded,
  isSelected,
  disabled,
  onClick,
}: {
  name: string
  tableCount: number
  isLoaded: boolean
  isSelected: boolean
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isLoaded || disabled}
      className={`relative p-3 rounded-lg border-2 text-left transition-all ${
        isLoaded
          ? 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
          : isSelected
          ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-500 ring-offset-1'
          : 'bg-white border-gray-200 hover:border-gray-300 text-gray-700'
      } ${disabled && !isLoaded ? 'opacity-60 cursor-not-allowed' : ''}`}
    >
      {isLoaded && (
        <div className="absolute top-1.5 right-1.5">
          <svg className="w-4 h-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      )}
      {isSelected && !isLoaded && (
        <div className="absolute top-1.5 right-1.5">
          <svg className="w-4 h-4 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      )}
      <p className="font-medium text-sm truncate pr-5">{name}</p>
      <p className={`text-xs mt-1 ${isLoaded ? 'text-gray-400' : isSelected ? 'text-blue-600' : 'text-gray-500'}`}>
        {tableCount} table{tableCount !== 1 ? 's' : ''}
        {isLoaded ? ' (loaded)' : ''}
      </p>
    </button>
  )
}

// --- Schema Merge Utility ---

function mergeSchemas(schemas: DatabaseSchema[]): DatabaseSchema | null {
  if (schemas.length === 0) return null
  if (schemas.length === 1) return schemas[0]

  const allTables = schemas.flatMap(s => s.tables)
  const allFks = schemas.flatMap(s => s.foreign_keys)

  // Deduplicate tables by schema_name.table_name
  const tableMap = new Map<string, typeof allTables[number]>()
  for (const t of allTables) {
    tableMap.set(`${t.schema_name}.${t.table_name}`, t)
  }
  const mergedTables = Array.from(tableMap.values())

  // Deduplicate FKs by constraint_name
  const fkMap = new Map<string, typeof allFks[number]>()
  for (const fk of allFks) {
    fkMap.set(fk.constraint_name, fk)
  }
  const mergedFks = Array.from(fkMap.values())

  return {
    database_name: schemas[0].database_name,
    tables: mergedTables,
    foreign_keys: mergedFks,
    extraction_time_seconds: schemas.reduce((sum, s) => sum + s.extraction_time_seconds, 0),
    table_count: mergedTables.length,
    standalone_table_count: 0,
  }
}
