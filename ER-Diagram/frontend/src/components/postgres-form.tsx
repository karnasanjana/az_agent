'use client'

import { useActionState, useEffect, useRef, useState } from 'react'
import { listPostgresDatabases, testPostgresConnection, type ConnectionState } from '@/app/actions'
import DatabasePicker from '@/components/database-picker'
import type { DatabaseInfo } from '@/types/schema'

const initialState: ConnectionState = { success: null, message: '', error_code: null }
type Credentials = { host: string; port: number; database: string; username: string; password: string }

export default function PostgresForm() {
  const [state, action, pending] = useActionState(testPostgresConnection, initialState)
  const form = useRef<HTMLFormElement>(null)
  const credentials = useRef<Credentials | null>(null)
  const [databases, setDatabases] = useState<DatabaseInfo[] | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const capture = () => {
    const data = new FormData(form.current!)
    credentials.current = { host: String(data.get('host')), port: Number(data.get('port')), database: String(data.get('database')), username: String(data.get('username')), password: String(data.get('password')) }
  }
  useEffect(() => {
    if (!state.success || !credentials.current) return
    const creds = credentials.current
    sessionStorage.setItem('db_credentials', JSON.stringify(creds))
    sessionStorage.setItem('db_type', 'postgres')
    listPostgresDatabases(creds).then(({ databases }) => { if (databases) { setDatabases(databases); setSelected([creds.database]) } })
  }, [state.success])
  const fields = [
    ['host','Server Host','localhost','text'], ['port','Port','5432','number'], ['database','Database Name','retail_db','text'],
    ['username','Username','postgres','text'], ['password','Password','Password','password'],
  ]
  return <div className="max-w-md mx-auto animate-fadeIn">
    {!state.success && <form ref={form} action={action} onSubmit={capture} className="p-6 glass-panel rounded-2xl space-y-4">
      {fields.map(([name,label,placeholder,type]) => <div key={name}>
        <label htmlFor={`pg-${name}`} className="block text-sm font-medium text-slate-300 mb-1">{label}</label>
        <input id={`pg-${name}`} name={name} type={type} required placeholder={placeholder} defaultValue={name === 'port' ? 5432 : ''}
          className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50" />
      </div>)}
      <button disabled={pending} className="w-full py-2.5 px-4 bg-gradient-to-r from-blue-500 to-cyan-600 text-white rounded-lg font-medium disabled:opacity-50">{pending ? 'Testing Connection...' : 'Test PostgreSQL Connection'}</button>
      {state.success === false && <div className="p-3 bg-red-900/40 border border-red-500/30 text-red-200 rounded-lg text-sm">{state.message}</div>}
    </form>}
    {state.success && <div className="p-6 glass-panel rounded-2xl">
      <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-500/30 text-emerald-200 rounded-lg text-sm">{state.message}</div>
      {databases ? <>
        <DatabasePicker databases={databases} selectedDatabases={selected} onSelect={setSelected} label="databases" />
        <button disabled={!selected.length} onClick={() => { sessionStorage.setItem('selected_databases', JSON.stringify(selected)); window.location.href='/extract' }} className="mt-6 w-full py-2.5 px-4 bg-gradient-to-r from-blue-500 to-cyan-600 text-white rounded-lg disabled:opacity-50">Next: Extract Schema →</button>
      </> : <div className="text-center py-6"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400 mx-auto mb-3" /><p className="text-sm text-slate-400">Loading databases...</p></div>}
    </div>}
  </div>
}
