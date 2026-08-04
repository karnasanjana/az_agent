'use client'

import { useState } from 'react'
import { useSession, signIn } from 'next-auth/react'
import { listGcsFiles } from '@/app/actions'
import type { DatabaseInfo } from '@/types/schema'
import DatabasePicker from '@/components/database-picker'

export default function GcsForm() {
  const { data: session } = useSession()
  const accessToken = (session as { accessToken?: string } | null)?.accessToken

  const [bucket, setBucket] = useState('')
  const [prefix, setPrefix] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [files, setFiles] = useState<DatabaseInfo[] | null>(null)
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])

  const handleConnect = async () => {
    const b = bucket.trim().replace(/^gs:\/\//, '').replace(/\/+$/, '')
    if (!b) return
    if (!accessToken) {
      setError('Google sign-in required. Sign in with the Google account that can read this bucket.')
      return
    }
    setConnecting(true)
    setError(null)
    setFiles(null)
    try {
      const result = await listGcsFiles(b, prefix.trim(), accessToken)
      if (result.files) {
        setFiles(result.files)
        sessionStorage.setItem('db_type', 'gcs')
        sessionStorage.setItem('gcs_bucket', b)
        sessionStorage.setItem('gcs_prefix', prefix.trim())
        sessionStorage.setItem('gcs_access_token', accessToken)
      } else {
        setError(result.error || 'Failed to list files')
      }
    } catch {
      setError('Failed to connect to Cloud Storage. Check the bucket name and try again.')
    } finally {
      setConnecting(false)
    }
  }

  const handleProceed = () => {
    sessionStorage.setItem('selected_databases', JSON.stringify(selectedFiles))
    window.location.href = '/extract'
  }

  return (
    <div className="max-w-md mx-auto animate-fadeIn">
      {!files && (
      <div className="p-6 glass-panel rounded-2xl">
        <div className="space-y-4">
          <div>
            <label htmlFor="gcsBucket" className="block text-sm font-medium text-slate-300 mb-1">
              Bucket name
            </label>
            <input
              type="text"
              id="gcsBucket"
              value={bucket}
              onChange={(e) => setBucket(e.target.value)}
              placeholder="my-data-bucket"
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all text-slate-200"
            />
          </div>

          <div>
            <label htmlFor="gcsPrefix" className="block text-sm font-medium text-slate-300 mb-1">
              Folder / prefix <span className="text-slate-500">(optional)</span>
            </label>
            <input
              type="text"
              id="gcsPrefix"
              value={prefix}
              onChange={(e) => setPrefix(e.target.value)}
              placeholder="raw/2024/"
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all text-slate-200"
            />
            <p className="mt-1 text-xs text-slate-500">
              Lists CSV/JSON/Parquet files; each becomes a table.
            </p>
          </div>

          {!accessToken ? (
            <div className="space-y-3">
              <div className="p-3 bg-amber-900/40 border border-amber-500/30 rounded-lg backdrop-blur-sm">
                <p className="text-sm text-amber-200">
                  Sign in with Google to access Cloud Storage. Your account needs read access to the bucket.
                </p>
              </div>
              <button
                type="button"
                onClick={() => signIn('google')}
                className="w-full py-2.5 px-4 bg-slate-800 border border-slate-700 text-slate-200 rounded-lg hover:bg-slate-700 hover:border-slate-600 transition-all font-medium flex items-center justify-center gap-3 shadow-[0_0_10px_rgba(0,0,0,0.2)]"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
                Sign in with Google
              </button>
            </div>
          ) : (
            <div className="p-2.5 bg-emerald-900/40 border border-emerald-500/30 rounded-lg backdrop-blur-sm">
              <p className="text-xs text-emerald-200 flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Signed in as {session?.user?.email || 'Google account'}
              </p>
            </div>
          )}

          <button
            type="button"
            onClick={handleConnect}
            disabled={connecting || !bucket.trim() || !accessToken}
            className="w-full py-2.5 px-4 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.5)] border border-white/10 hover:from-blue-400 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
          >
            {connecting ? 'Connecting...' : 'List files'}
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-900/40 border border-red-500/30 text-red-200 rounded-lg backdrop-blur-sm text-sm">
            {error}
          </div>
        )}
      </div>
      )}

      {files && (
        <div className="mt-6 p-6 glass-panel rounded-2xl animate-fadeIn">
          <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-500/30 text-emerald-200 rounded-lg backdrop-blur-sm text-sm">
            Connected to: gs://{bucket.trim().replace(/^gs:\/\//, '')}{prefix.trim() ? '/' + prefix.trim() : ''}
          </div>

          {files.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-4">
              No CSV/JSON/Parquet files found in this bucket/prefix.
            </p>
          ) : (
            <>
              <DatabasePicker
                databases={files}
                onSelect={setSelectedFiles}
                selectedDatabases={selectedFiles}
                label="files"
              />
              <button
                onClick={handleProceed}
                disabled={selectedFiles.length === 0}
                className="mt-6 w-full py-2.5 px-4 bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-center rounded-lg shadow-[0_0_15px_rgba(59,130,246,0.5)] border border-white/10 hover:from-blue-400 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
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
