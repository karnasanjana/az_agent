'use server'

import type { StartExtractionResponse, DatabaseInfo } from '@/types/schema'
import type { DiagramMetadata } from '@/types/diagram'
import { auth } from '@/lib/auth'

const API_BASE = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'
const NETWORK_ERROR_MSG = 'Unable to reach the server. Please make sure the backend is running and try again.'

export type ConnectionState = {
  success: boolean | null
  message: string
  error_code: string | null
  // Preserve field values on error (except password)
  fields?: {
    host: string
    port: number
    database: string
    username: string
  }
}

export async function testConnection(
  prevState: ConnectionState,
  formData: FormData
): Promise<ConnectionState> {
  // Extract fields from formData
  const host = formData.get('host') as string
  const portStr = formData.get('port') as string
  const port = parseInt(portStr, 10)
  const database = formData.get('database') as string
  const username = formData.get('username') as string
  const password = formData.get('password') as string

  // Store field values to return on error (except password)
  const fields = { host, port, database, username }

  try {
    const response = await fetch(`${API_BASE}/api/connection/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, database, username, password }),
    })

    const data = await response.json()

    if (!response.ok) {
      return {
        success: false,
        message: data.detail || data.message || 'Connection failed',
        error_code: data.error_code || 'CONNECTION_ERROR',
        fields,
      }
    }

    return {
      success: true,
      message: data.message || 'Connection successful!',
      error_code: null,
      fields,
    }
  } catch (error) {
    return {
      success: false,
      message: NETWORK_ERROR_MSG,
      error_code: 'NETWORK_ERROR',
      fields,
    }
  }
}

export async function testPostgresConnection(prevState: ConnectionState, formData: FormData): Promise<ConnectionState> {
  const host = formData.get('host') as string
  const port = parseInt(formData.get('port') as string, 10)
  const database = formData.get('database') as string
  const username = formData.get('username') as string
  const password = formData.get('password') as string
  const fields = { host, port, database, username }
  try {
    const response = await fetch(`${API_BASE}/api/postgres/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ host, port, database, username, password }) })
    const data = await response.json()
    return { success: Boolean(data.success), message: data.message || 'Connection failed', error_code: data.error_code, fields }
  } catch { return { success: false, message: NETWORK_ERROR_MSG, error_code: 'NETWORK_ERROR', fields } }
}

export async function listPostgresDatabases(credentials: { host: string; port: number; database: string; username: string; password: string }): Promise<{ databases: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/postgres/databases`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) })
    const data = await response.json()
    return response.ok ? { databases: data, error: null } : { databases: null, error: data.detail || 'Failed to inspect database' }
  } catch { return { databases: null, error: NETWORK_ERROR_MSG } }
}

export async function startPostgresExtraction(credentials: { host: string; port: number; database: string; username: string; password: string }): Promise<StartExtractionResponse> {
  const response = await fetch(`${API_BASE}/api/postgres/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) })
  if (!response.ok) throw new Error((await response.json()).detail || 'Failed to start PostgreSQL extraction')
  return response.json()
}

export async function fetchPostgresSchema(streamId: string): Promise<{ schemaJson: string | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/postgres/stream/${streamId}`, { headers: { Accept: 'text/event-stream' } })
    const lines = (await response.text()).split('\n')
    let result = false
    for (const line of lines) {
      if (line === 'event: result') { result = true; continue }
      if (result && line.startsWith('data: ')) return { schemaJson: line.slice(6), error: null }
      if (line === 'event: error') result = false
    }
    return { schemaJson: null, error: 'No PostgreSQL schema data received' }
  } catch (err) { return { schemaJson: null, error: err instanceof Error ? err.message : 'Extraction failed' } }
}

export async function startExtraction(credentials: {
  host: string
  port: number
  database: string
  username: string
  password: string
}): Promise<StartExtractionResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/schema/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    })
    return response.json()
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

export async function fetchExtractedSchema(streamId: string): Promise<{
  schemaJson: string | null
  error: string | null
}> {
  try {
    const response = await fetch(`${API_BASE}/api/schema/stream/${streamId}`, {
      headers: { 'Accept': 'text/event-stream' },
    })

    if (!response.body) {
      return { schemaJson: null, error: 'No response body from server' }
    }

    // Read the full streaming response
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
    }
    fullText += decoder.decode() // flush

    // Parse SSE events to find the "result" event with the schema
    const lines = fullText.split('\n')
    let nextIsResult = false
    for (const line of lines) {
      if (line === 'event: result') {
        nextIsResult = true
        continue
      }
      if (nextIsResult && line.startsWith('data: ')) {
        const jsonStr = line.substring(6)
        const schema = JSON.parse(jsonStr)
        return { schemaJson: jsonStr, error: null }
      }
      if (line === 'event: error') {
        nextIsResult = false
      }
    }
    return { schemaJson: null, error: 'No schema data received from extraction' }
  } catch (err) {
    return { schemaJson: null, error: `Extraction failed: ${err instanceof Error ? err.message : 'Unknown error'}` }
  }
}

export async function confirmExtraction(streamId: string): Promise<{ success: boolean }> {
  try {
    const response = await fetch(`${API_BASE}/api/schema/confirm/${streamId}`, {
      method: 'POST',
    })
    return response.json()
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

// --- Diagram Persistence Actions ---

async function getAuthHeaders(): Promise<{ 'Content-Type': string; 'X-User-ID': string }> {
  const session = await auth()
  if (!session?.user?.email) {
    throw new Error('Not authenticated')
  }
  return {
    'Content-Type': 'application/json',
    'X-User-ID': session.user.email,
  }
}

export async function saveDiagram(
  name: string,
  diagramData: object
): Promise<DiagramMetadata> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ name, diagram: diagramData }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || 'Failed to save diagram')
    }

    return response.json()
  } catch (error) {
    if (error instanceof Error && error.message !== 'Not authenticated') {
      throw new Error(`Failed to save diagram: ${error.message}`)
    }
    throw error
  }
}

export async function saveDiagramSql(
  diagramId: string,
  sql: string
): Promise<void> {
  try {
    const headers = await getAuthHeaders()
    await fetch(`${API_BASE}/api/diagrams/${diagramId}/sql`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ sql }),
    })
  } catch {
    // Non-critical — don't fail the save if SQL save fails
  }
}

export async function updateDiagram(
  diagramId: string,
  name: string,
  diagramData: object
): Promise<DiagramMetadata> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ name, diagram: diagramData }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      if (response.status === 404) {
        throw new Error('Diagram not found')
      }
      throw new Error(data.detail || 'Failed to update diagram')
    }

    return response.json()
  } catch (error) {
    if (error instanceof Error && (error.message === 'Not authenticated' || error.message === 'Diagram not found')) {
      throw error
    }
    throw new Error(`Failed to update diagram: ${error instanceof Error ? error.message : 'Unknown error'}`)
  }
}

export async function listDiagrams(): Promise<DiagramMetadata[]> {
  try {
    const headers = await getAuthHeaders()
    console.log('[listDiagrams] Fetching with user:', headers['X-User-ID'], 'API:', API_BASE)
    const response = await fetch(`${API_BASE}/api/diagrams`, {
      method: 'GET',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })

    if (!response.ok) {
      console.error('[listDiagrams] Failed:', response.status, await response.text())
      return []
    }

    const data = await response.json()
    console.log('[listDiagrams] Got', data.length, 'diagrams')
    return data
  } catch (err) {
    console.error('[listDiagrams] Error:', err)
    return []
  }
}

export async function loadDiagram(
  diagramId: string
): Promise<{ metadata: DiagramMetadata; diagram: object }> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}`, {
      method: 'GET',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Diagram not found')
      }
      throw new Error('Failed to load diagram')
    }

    return response.json()
  } catch (error) {
    if (error instanceof Error && (error.message === 'Not authenticated' || error.message === 'Diagram not found')) {
      throw error
    }
    throw new Error(`Failed to load diagram: ${error instanceof Error ? error.message : 'Unknown error'}`)
  }
}

export async function deleteDiagram(
  diagramId: string
): Promise<{ success: boolean }> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}`, {
      method: 'DELETE',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Diagram not found')
      }
      throw new Error('Failed to delete diagram')
    }

    return { success: true }
  } catch (error) {
    if (error instanceof Error && (error.message === 'Not authenticated' || error.message === 'Diagram not found')) {
      throw error
    }
    throw new Error(`Failed to delete diagram: ${error instanceof Error ? error.message : 'Unknown error'}`)
  }
}

// --- Schema Change History ---

export async function getDiagramHistory(
  diagramId: string
): Promise<{ history: object[] }> {
  const headers = await getAuthHeaders()
  const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}/history`, {
    method: 'GET',
    headers: { 'X-User-ID': headers['X-User-ID'] },
  })
  if (!response.ok) return { history: [] }
  return response.json()
}

// --- Database/Dataset Listing Actions ---

export async function listSqlServerDatabases(credentials: {
  host: string
  port: number
  database?: string
  username: string
  password: string
}): Promise<{ databases: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/connection/databases`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { databases: null, error: data.detail || data.message || 'Failed to list databases' }
    }

    const data = await response.json()
    return { databases: data.databases ?? data, error: null }
  } catch {
    return { databases: null, error: NETWORK_ERROR_MSG }
  }
}

export async function listBigQueryDatasets(
  projectId: string,
  accessToken: string
): Promise<{ datasets: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/bigquery/datasets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, access_token: accessToken }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { datasets: null, error: data.detail || data.message || 'Failed to list datasets' }
    }

    const data = await response.json()
    return { datasets: data.datasets ?? data, error: null }
  } catch {
    return { datasets: null, error: NETWORK_ERROR_MSG }
  }
}

export async function startBigQueryExtraction(
  projectId: string,
  accessToken: string,
  datasets: string[]
): Promise<StartExtractionResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/bigquery/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, access_token: accessToken, datasets }),
    })
    const text = await response.text()
    let data: StartExtractionResponse & { detail?: string }
    try {
      data = JSON.parse(text)
    } catch {
      throw new Error(response.ok ? 'BigQuery returned an invalid response' : `BigQuery extraction could not start (HTTP ${response.status})`)
    }
    if (!response.ok) {
      throw new Error(data.detail || `BigQuery extraction could not start (HTTP ${response.status})`)
    }
    return data
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

export async function fetchBigQuerySchema(streamId: string): Promise<{
  schemaJson: string | null
  error: string | null
}> {
  try {
    const response = await fetch(`${API_BASE}/api/bigquery/stream/${streamId}`, {
      headers: { 'Accept': 'text/event-stream' },
    })

    if (!response.body) {
      return { schemaJson: null, error: 'No response body from server' }
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
    }
    fullText += decoder.decode()

    const lines = fullText.split('\n')
    let nextIsResult = false
    for (const line of lines) {
      if (line === 'event: result') {
        nextIsResult = true
        continue
      }
      if (nextIsResult && line.startsWith('data: ')) {
        const jsonStr = line.substring(6)
        return { schemaJson: jsonStr, error: null }
      }
      if (line === 'event: error') {
        nextIsResult = false
      }
    }
    return { schemaJson: null, error: 'No schema data received from extraction' }
  } catch (err) {
    return { schemaJson: null, error: `Extraction failed: ${err instanceof Error ? err.message : 'Unknown error'}` }
  }
}


// --- GCS (Cloud Storage bucket) Actions — reuse the Google sign-in token ---

export async function listGcsFiles(
  bucket: string,
  prefix: string,
  accessToken: string
): Promise<{ files: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/gcs/files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bucket, prefix, access_token: accessToken }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { files: null, error: data.detail || data.message || 'Failed to list files' }
    }
    const data = await response.json()
    return { files: data.files ?? data, error: null }
  } catch {
    return { files: null, error: NETWORK_ERROR_MSG }
  }
}

export async function startGcsExtraction(
  bucket: string,
  prefix: string,
  accessToken: string,
  files: string[]
): Promise<StartExtractionResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/gcs/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bucket, prefix, access_token: accessToken, files }),
    })
    return response.json()
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

export async function fetchGcsSchema(streamId: string): Promise<{
  schemaJson: string | null
  error: string | null
}> {
  try {
    const response = await fetch(`${API_BASE}/api/gcs/stream/${streamId}`, {
      headers: { 'Accept': 'text/event-stream' },
    })
    if (!response.body) return { schemaJson: null, error: 'No response body from server' }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
    }
    fullText += decoder.decode()

    const lines = fullText.split('\n')
    let nextIsResult = false
    for (const line of lines) {
      if (line === 'event: result') { nextIsResult = true; continue }
      if (nextIsResult && line.startsWith('data: ')) {
        return { schemaJson: line.substring(6), error: null }
      }
      if (line === 'event: error') nextIsResult = false
    }
    return { schemaJson: null, error: 'No schema data received from extraction' }
  } catch (err) {
    return { schemaJson: null, error: `Extraction failed: ${err instanceof Error ? err.message : 'Unknown error'}` }
  }
}

// --- Dataverse Actions ---

export async function listDataverseEntities(
  environmentUrl: string,
  accessToken: string
): Promise<{ entities: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/dataverse/entities`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ environment_url: environmentUrl, access_token: accessToken }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { entities: null, error: data.detail || data.message || 'Failed to list entities' }
    }

    const data = await response.json()
    return { entities: data.entities ?? data, error: null }
  } catch {
    return { entities: null, error: NETWORK_ERROR_MSG }
  }
}

export async function startDataverseExtraction(
  environmentUrl: string,
  accessToken: string,
  entities: string[]
): Promise<StartExtractionResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/dataverse/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ environment_url: environmentUrl, access_token: accessToken, entities }),
    })
    return response.json()
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

export async function fetchDataverseSchema(streamId: string): Promise<{
  schemaJson: string | null
  error: string | null
}> {
  try {
    const response = await fetch(`${API_BASE}/api/dataverse/stream/${streamId}`, {
      headers: { 'Accept': 'text/event-stream' },
    })

    if (!response.body) {
      return { schemaJson: null, error: 'No response body from server' }
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
    }
    fullText += decoder.decode()

    const lines = fullText.split('\n')
    let nextIsResult = false
    for (const line of lines) {
      if (line === 'event: result') {
        nextIsResult = true
        continue
      }
      if (nextIsResult && line.startsWith('data: ')) {
        const jsonStr = line.substring(6)
        return { schemaJson: jsonStr, error: null }
      }
      if (line === 'event: error') {
        nextIsResult = false
      }
    }
    return { schemaJson: null, error: 'No schema data received from extraction' }
  } catch (err) {
    return { schemaJson: null, error: `Extraction failed: ${err instanceof Error ? err.message : 'Unknown error'}` }
  }
}

// --- SharePoint Actions (mirror Dataverse; Microsoft Graph, delegated token) ---

export async function listSharePointLists(
  siteUrl: string,
  accessToken: string
): Promise<{ lists: DatabaseInfo[] | null; error: string | null }> {
  try {
    const response = await fetch(`${API_BASE}/api/sharepoint/lists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_url: siteUrl, access_token: accessToken }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { lists: null, error: data.detail || data.message || 'Failed to list lists' }
    }
    const data = await response.json()
    return { lists: data.lists ?? data, error: null }
  } catch {
    return { lists: null, error: NETWORK_ERROR_MSG }
  }
}

export async function startSharePointExtraction(
  siteUrl: string,
  accessToken: string,
  lists: string[]
): Promise<StartExtractionResponse> {
  try {
    const response = await fetch(`${API_BASE}/api/sharepoint/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ site_url: siteUrl, access_token: accessToken, lists }),
    })
    return response.json()
  } catch {
    throw new Error(NETWORK_ERROR_MSG)
  }
}

export async function fetchSharePointSchema(streamId: string): Promise<{
  schemaJson: string | null
  error: string | null
}> {
  try {
    const response = await fetch(`${API_BASE}/api/sharepoint/stream/${streamId}`, {
      headers: { 'Accept': 'text/event-stream' },
    })
    if (!response.body) return { schemaJson: null, error: 'No response body from server' }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let fullText = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      fullText += decoder.decode(value, { stream: true })
    }
    fullText += decoder.decode()

    const lines = fullText.split('\n')
    let nextIsResult = false
    for (const line of lines) {
      if (line === 'event: result') { nextIsResult = true; continue }
      if (nextIsResult && line.startsWith('data: ')) {
        return { schemaJson: line.substring(6), error: null }
      }
      if (line === 'event: error') nextIsResult = false
    }
    return { schemaJson: null, error: 'No schema data received from extraction' }
  } catch (err) {
    return { schemaJson: null, error: `Extraction failed: ${err instanceof Error ? err.message : 'Unknown error'}` }
  }
}

// --- Sharing Actions ---

export async function shareDiagram(
  diagramId: string
): Promise<{ share_token?: string; error?: string }> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}/share`, {
      method: 'POST',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { error: data.detail || 'Failed to share diagram' }
    }
    return response.json()
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Failed to share diagram' }
  }
}

export async function unshareDiagram(
  diagramId: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}/share`, {
      method: 'DELETE',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { success: false, error: data.detail || 'Failed to unshare diagram' }
    }
    return { success: true }
  } catch (err) {
    return { success: false, error: err instanceof Error ? err.message : 'Failed to unshare diagram' }
  }
}

export async function updateShareSettings(
  diagramId: string,
  showRelationships: boolean,
  shareNote: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}/share`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        show_relationships: showRelationships,
        share_note: shareNote,
      }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      return { success: false, error: data.detail || 'Failed to update share settings' }
    }
    return { success: true }
  } catch (err) {
    return { success: false, error: err instanceof Error ? err.message : 'Failed to update share settings' }
  }
}

export async function loadSharedDiagram(
  shareToken: string
): Promise<{ metadata: DiagramMetadata; diagram: object }> {
  const response = await fetch(`${API_BASE}/api/diagrams/shared/${shareToken}`, {
    method: 'GET',
  })
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Shared diagram not found or link expired')
    }
    throw new Error('Failed to load shared diagram')
  }
  return response.json()
}

// --- Impact Analysis Action ---

export async function analyzeImpact(
  schema: object,
  targetTable: string,
  targetColumn?: string | null
): Promise<object> {
  const response = await fetch(`${API_BASE}/api/chat/impact-analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      schema,
      target_table: targetTable,
      target_column: targetColumn || null,
    }),
  })
  if (!response.ok) {
    throw new Error('Impact analysis failed')
  }
  return response.json()
}

// --- Auto-Document Action ---

export async function autoDocumentSchema(
  schema: object
): Promise<{ schema?: object; error?: string }> {
  try {
    const response = await fetch(`${API_BASE}/api/chat/auto-document`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schema }),
    })
    if (!response.ok) {
      const text = await response.text()
      return { error: text || `Auto-document request failed: ${response.status}` }
    }
    return response.json()
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Auto-document failed' }
  }
}

// --- Infer Relationships Action ---

export async function inferRelationships(
  schema: object
): Promise<object> {
  const response = await fetch(`${API_BASE}/api/chat/infer-relationships`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schema }),
  })
  if (!response.ok) {
    throw new Error('Infer relationships failed')
  }
  return response.json()
}

// --- API Base URL for client components ---

export async function getApiBaseUrl(): Promise<string> {
  return API_BASE
}

export async function getDiagramSql(diagramId: string): Promise<string | null> {
  try {
    const headers = await getAuthHeaders()
    const response = await fetch(`${API_BASE}/api/diagrams/${diagramId}/sql`, {
      method: 'GET',
      headers: { 'X-User-ID': headers['X-User-ID'] },
    })
    if (!response.ok) return null
    const data = await response.json()
    return data.sql || null
  } catch {
    return null
  }
}
