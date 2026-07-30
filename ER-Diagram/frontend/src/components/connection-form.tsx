'use client'

import { useActionState, useRef, useEffect, useState } from 'react'
import { testConnection, listSqlServerDatabases, type ConnectionState } from '@/app/actions'
import type { DatabaseInfo } from '@/types/schema'
import DatabasePicker from '@/components/database-picker'

const initialState: ConnectionState = {
  success: null,
  message: '',
  error_code: null,
}

export default function ConnectionForm() {
  const [state, formAction, pending] = useActionState(testConnection, initialState)
  const formRef = useRef<HTMLFormElement>(null)
  const pendingCredentialsRef = useRef<{host: string; port: number; database: string; username: string; password: string} | null>(null)

  const [databases, setDatabases] = useState<DatabaseInfo[] | null>(null)
  const [selectedDatabases, setSelectedDatabases] = useState<string[]>([])
  const [loadingDatabases, setLoadingDatabases] = useState(false)
  const [dbError, setDbError] = useState<string | null>(null)

  // Capture credentials before form submission (React 19 resets form after useActionState)
  const handleSubmit = () => {
    if (formRef.current) {
      const formData = new FormData(formRef.current)
      pendingCredentialsRef.current = {
        host: formData.get('host') as string,
        port: parseInt(formData.get('port') as string, 10),
        database: formData.get('database') as string,
        username: formData.get('username') as string,
        password: formData.get('password') as string,
      }
    }
  }

  // When connection succeeds, store credentials and fetch database list
  useEffect(() => {
    if (state.success === true && pendingCredentialsRef.current) {
      const creds = pendingCredentialsRef.current
      sessionStorage.setItem('db_credentials', JSON.stringify(creds))
      sessionStorage.setItem('db_type', 'sqlserver')

      // Fetch databases list
      setLoadingDatabases(true)
      setDbError(null)
      listSqlServerDatabases({
        host: creds.host,
        port: creds.port,
        database: creds.database,
        username: creds.username,
        password: creds.password,
      }).then((result) => {
        if (result.databases) {
          setDatabases(result.databases)
          // Pre-select the database from the connection form if it exists in the list
          const match = result.databases.find(
            (db) => db.name.toLowerCase() === creds.database.toLowerCase()
          )
          if (match) {
            setSelectedDatabases([match.name])
          }
        } else {
          setDbError(result.error || 'Failed to list databases')
          // Fallback: use the single database from the form
          setDatabases([{ name: creds.database, table_count: 0 }])
          setSelectedDatabases([creds.database])
        }
      }).finally(() => {
        setLoadingDatabases(false)
      })

      pendingCredentialsRef.current = null
    }
  }, [state.success])

  const handleProceed = () => {
    sessionStorage.setItem('selected_databases', JSON.stringify(selectedDatabases))
    window.location.href = '/extract'
  }

  return (
    <div className="max-w-md mx-auto animate-fadeIn">
      <form ref={formRef} action={formAction} onSubmit={handleSubmit} className="p-6 glass-panel rounded-2xl">
        <div className="space-y-4">
          {/* Host Field */}
          <div>
            <label htmlFor="host" className="block text-sm font-medium text-slate-300 mb-1">
              Server Host
            </label>
            <input
              type="text"
              id="host"
              name="host"
              required
              placeholder="Server hostname"
              defaultValue={state.fields?.host || ''}
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Port Field */}
          <div>
            <label htmlFor="port" className="block text-sm font-medium text-slate-300 mb-1">
              Port
            </label>
            <input
              type="number"
              id="port"
              name="port"
              required
              defaultValue={state.fields?.port || 1433}
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Database Field */}
          <div>
            <label htmlFor="database" className="block text-sm font-medium text-slate-300 mb-1">
              Database Name
            </label>
            <input
              type="text"
              id="database"
              name="database"
              required
              placeholder="Database name"
              defaultValue={state.fields?.database || ''}
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Username Field */}
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-slate-300 mb-1">
              Username
            </label>
            <input
              type="text"
              id="username"
              name="username"
              required
              placeholder="Username"
              defaultValue={state.fields?.username || ''}
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Password Field */}
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1">
              Password
            </label>
            <input
              type="password"
              id="password"
              name="password"
              required
              placeholder="Password"
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all"
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={pending}
            aria-busy={pending}
            className="w-full py-2.5 px-4 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg font-medium shadow-[0_0_15px_rgba(99,102,241,0.5)] border border-white/10 hover:from-indigo-400 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {pending ? 'Testing Connection...' : 'Test Connection'}
          </button>
        </div>

        {/* Status Display */}
        <div role="status" aria-live="polite">
          {state.success === false && (
            <div className="mt-4 p-3 bg-red-900/40 border border-red-500/30 text-red-200 rounded-lg backdrop-blur-sm text-sm">
              {state.message}
            </div>
          )}
        </div>
      </form>

      {/* Database Picker (appears after successful connection) */}
      {state.success === true && (
        <div className="mt-6 p-6 glass-panel rounded-2xl animate-fadeIn">
          <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-500/30 text-emerald-200 rounded-lg backdrop-blur-sm text-sm">
            {state.message}
          </div>

          {loadingDatabases && (
            <div className="text-center py-6">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-400 mx-auto mb-3"></div>
              <p className="text-sm text-slate-400">Loading databases...</p>
            </div>
          )}

          {dbError && !databases && (
            <div className="p-3 bg-amber-900/40 border border-amber-500/30 text-amber-200 rounded-lg backdrop-blur-sm text-sm">
              {dbError}
            </div>
          )}

          {databases && !loadingDatabases && (
            <>
              <DatabasePicker
                databases={databases}
                onSelect={setSelectedDatabases}
                selectedDatabases={selectedDatabases}
                label="databases"
              />
              <button
                onClick={handleProceed}
                disabled={selectedDatabases.length === 0}
                className="mt-6 w-full py-2.5 px-4 bg-gradient-to-r from-indigo-500 to-purple-600 text-white text-center rounded-lg shadow-[0_0_15px_rgba(99,102,241,0.5)] border border-white/10 hover:from-indigo-400 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
              >
                Next: Extract Schema →
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
