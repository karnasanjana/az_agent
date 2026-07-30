// frontend/src/lib/schema-cache.ts
// Schema caching utilities using localStorage with TTL expiration

import type { DatabaseSchema } from '@/types/schema'

interface CacheEntry {
  schema: DatabaseSchema
  timestamp: number
}

const CACHE_TTL_MS = 10 * 60 * 1000 // 10 minutes

/**
 * Generate a cache key for a data source.
 * Format: "schema_cache:bq:{projectId}:{dataset}" or "schema_cache:sql:{host}:{database}"
 */
export function getCacheKey(type: 'bigquery' | 'sqlserver' | 'dataverse', ...parts: string[]): string {
  const prefix = type === 'bigquery' ? 'bq' : type === 'dataverse' ? 'dv' : 'sql'
  return `schema_cache:${prefix}:${parts.join(':')}`
}

/**
 * Get cached schema if it exists and hasn't expired.
 */
export function getCachedSchema(key: string): DatabaseSchema | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const entry: CacheEntry = JSON.parse(raw)
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(key)
      return null
    }
    return entry.schema
  } catch {
    return null
  }
}

/**
 * Cache a schema in localStorage with timestamp.
 */
export function setCachedSchema(key: string, schema: DatabaseSchema): void {
  const entry: CacheEntry = { schema, timestamp: Date.now() }
  try {
    localStorage.setItem(key, JSON.stringify(entry))
  } catch {
    // localStorage might be full, silently fail
  }
}

/**
 * Clear all cached schemas.
 */
export function clearSchemaCache(): void {
  const keys = Object.keys(localStorage).filter(k => k.startsWith('schema_cache:'))
  keys.forEach(k => localStorage.removeItem(k))
}
