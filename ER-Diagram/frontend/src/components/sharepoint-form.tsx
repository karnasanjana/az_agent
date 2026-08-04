'use client'

import { useState, useEffect } from 'react'
import { listSharePointLists } from '@/app/actions'
import type { DatabaseInfo } from '@/types/schema'
import DatabasePicker from '@/components/database-picker'
import { getMsalInstance } from '@/lib/msal'
import ClientIdField from '@/components/client-id-field'

const GRAPH_SCOPE = 'https://graph.microsoft.com/Sites.Read.All'

export default function SharePointForm() {
  const [siteUrl, setSiteUrl] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lists, setLists] = useState<DatabaseInfo[] | null>(null)
  const [selectedLists, setSelectedLists] = useState<string[]>([])
  const [signedInUser, setSignedInUser] = useState<string | null>(null)

  const fetchLists = async (url: string, token: string) => {
    setConnecting(true)
    try {
      const res = await listSharePointLists(url, token)
      if (res.lists) {
        setLists(res.lists)
        sessionStorage.setItem('db_type', 'sharepoint')
        sessionStorage.setItem('sp_site_url', url)
        sessionStorage.setItem('sp_access_token', token)
      } else {
        setError(res.error || 'Failed to list SharePoint lists')
      }
    } catch {
      setError('Failed to fetch lists after sign-in')
    } finally {
      setConnecting(false)
    }
  }

  // Handle the redirect back from Microsoft login.
  useEffect(() => {
    const savedUrl = sessionStorage.getItem('sp_pending_site_url')
    if (savedUrl) setSiteUrl(savedUrl)

    const { instance, ready } = getMsalInstance()
    ready.then(() => {
      instance.handleRedirectPromise().then(async (response) => {
        if (response && response.accessToken) {
          const token = response.accessToken
          setSignedInUser(response.account?.username || 'Microsoft account')
          if (window.location.hash) {
            window.history.replaceState(null, '', window.location.pathname)
          }
          const url = sessionStorage.getItem('sp_pending_site_url')
          if (url) {
            sessionStorage.removeItem('sp_pending_site_url')
            await fetchLists(url, token)
          }
        }
      }).catch(() => { /* no redirect to handle */ })
    })
  }, [])

  const handleSignIn = async () => {
    const url = siteUrl.trim().replace(/^https?:\/\//, '').replace(/\/+$/, '')
    if (!url) {
      setError('Please enter your SharePoint site URL first.')
      return
    }
    setError(null)
    setConnecting(true)
    try {
      const { instance, ready } = getMsalInstance()
      await ready

      const accounts = instance.getAllAccounts()
      if (accounts.length > 0) {
        try {
          const silent = await instance.acquireTokenSilent({ scopes: [GRAPH_SCOPE], account: accounts[0] })
          setSignedInUser(silent.account?.username || 'Microsoft account')
          await fetchLists(url, silent.accessToken)
          return
        } catch {
          // fall through to redirect
        }
      }

      sessionStorage.setItem('sp_pending_site_url', url)
      await instance.acquireTokenRedirect({ scopes: [GRAPH_SCOPE], prompt: 'select_account' })
      return
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Authentication failed'
      if (message.includes('user_cancelled') || message.includes('User cancelled')) {
        setError('Sign-in was cancelled. Please try again.')
      } else {
        setError(`Microsoft sign-in failed: ${message}`)
      }
    } finally {
      setConnecting(false)
    }
  }

  const handleProceed = () => {
    sessionStorage.setItem('selected_databases', JSON.stringify(selectedLists))
    window.location.href = '/extract'
  }

  return (
    <div className="max-w-md mx-auto animate-fadeIn">
      {!lists && (
      <div className="p-6 glass-panel rounded-2xl">
        <div className="space-y-4">
          <div>
            <label htmlFor="siteUrl" className="block text-sm font-medium text-slate-300 mb-1">
              SharePoint Site URL
            </label>
            <input
              type="text"
              id="siteUrl"
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
              placeholder="contoso.sharepoint.com/sites/Sales"
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-slate-200"
            />
            <p className="mt-1 text-xs text-slate-500">
              e.g. contoso.sharepoint.com/sites/Sales (without https://)
            </p>
          </div>

          <ClientIdField />

          {!signedInUser ? (
            <div className="space-y-3">
              <div className="p-3 bg-amber-900/40 border border-amber-500/30 rounded-lg backdrop-blur-sm">
                <p className="text-sm text-amber-200">
                  Sign in with your Microsoft account to access SharePoint. Your account must have read access to the site.
                </p>
              </div>
              <button
                type="button"
                onClick={handleSignIn}
                disabled={connecting || !siteUrl.trim()}
                className="w-full py-2.5 px-4 bg-slate-800 border border-slate-700 text-slate-200 rounded-lg hover:bg-slate-700 hover:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium flex items-center justify-center gap-3 shadow-[0_0_10px_rgba(0,0,0,0.2)]"
              >
                {connecting ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-indigo-400" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" viewBox="0 0 21 21">
                      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
                      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
                      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
                      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
                    </svg>
                    Connect with Microsoft
                  </>
                )}
              </button>
            </div>
          ) : (
            <div className="p-2.5 bg-emerald-900/40 border border-emerald-500/30 rounded-lg backdrop-blur-sm">
              <p className="text-xs text-emerald-200 flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Signed in as {signedInUser}
              </p>
            </div>
          )}
        </div>

        {error && (
          <div className="mt-4 p-3 bg-red-900/40 border border-red-500/30 text-red-200 rounded-lg backdrop-blur-sm text-sm">
            {error}
          </div>
        )}
      </div>
      )}

      {/* List Picker (replaces the connect box after a successful connection) */}
      {lists && (
        <div className="mt-6 p-6 glass-panel rounded-2xl animate-fadeIn">
          <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-500/30 text-emerald-200 rounded-lg backdrop-blur-sm text-sm">
            Connected to: {siteUrl.trim().replace(/^https?:\/\//, '')}
          </div>

          {lists.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-4">
              No lists found in this site.
            </p>
          ) : (
            <>
              <DatabasePicker
                databases={lists}
                onSelect={setSelectedLists}
                selectedDatabases={selectedLists}
                label="lists"
              />
              <button
                onClick={handleProceed}
                disabled={selectedLists.length === 0}
                className="mt-6 w-full py-2.5 px-4 bg-gradient-to-r from-indigo-500 to-indigo-600 text-white text-center rounded-lg shadow-[0_0_15px_rgba(68,147,248,0.5)] border border-white/10 hover:from-indigo-400 hover:to-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
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
