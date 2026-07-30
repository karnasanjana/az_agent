'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { PublicClientApplication, type AuthenticationResult } from '@azure/msal-browser'
import { listDataverseEntities } from '@/app/actions'
import type { DatabaseInfo } from '@/types/schema'
import DatabasePicker from '@/components/database-picker'

const MSAL_CLIENT_ID = '2967332b-4aa0-4a9a-89ca-596d6d54a009'

// Module-level singleton so MSAL is created exactly once across renders
let msalInstance: PublicClientApplication | null = null
let msalInitPromise: Promise<void> | null = null

function getMsalInstance(): { instance: PublicClientApplication; ready: Promise<void> } {
  if (!msalInstance) {
    msalInstance = new PublicClientApplication({
      auth: {
        clientId: MSAL_CLIENT_ID,
        authority: 'https://login.microsoftonline.com/common',
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    })
    msalInitPromise = msalInstance.initialize()
  }
  return { instance: msalInstance, ready: msalInitPromise! }
}

export default function DataverseForm() {
  const [environmentUrl, setEnvironmentUrl] = useState('')
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [entities, setEntities] = useState<DatabaseInfo[] | null>(null)
  const [selectedEntities, setSelectedEntities] = useState<string[]>([])
  const [signedInUser, setSignedInUser] = useState<string | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)

  // Handle redirect response on mount (after Microsoft login redirect)
  useEffect(() => {
    // Restore environment URL from sessionStorage (saved before redirect)
    const savedUrl = sessionStorage.getItem('dv_pending_env_url')
    if (savedUrl) setEnvironmentUrl(savedUrl)

    const { instance, ready } = getMsalInstance()
    ready.then(() => {
      instance.handleRedirectPromise().then(async (response) => {
        if (response && response.accessToken) {
          const token = response.accessToken
          setAccessToken(token)
          setSignedInUser(response.account?.username || 'Microsoft account')

          // Clean URL hash
          if (window.location.hash) {
            window.history.replaceState(null, '', window.location.pathname)
          }

          // Auto-fetch entities after redirect login
          const envUrl = sessionStorage.getItem('dv_pending_env_url')
          if (envUrl) {
            sessionStorage.removeItem('dv_pending_env_url')
            setConnecting(true)
            try {
              const res = await listDataverseEntities(envUrl, token)
              if (res.entities) {
                setEntities(res.entities)
                sessionStorage.setItem('db_type', 'dataverse')
                sessionStorage.setItem('dv_environment_url', envUrl)
                sessionStorage.setItem('dv_access_token', token)
              } else {
                setError(res.error || 'Failed to list entities')
              }
            } catch {
              setError('Failed to fetch entities after sign-in')
            } finally {
              setConnecting(false)
            }
          }
        }
      }).catch(() => {
        // No redirect response to handle
      })
    })
  }, [])

  const handleSignIn = async () => {
    const envUrl = environmentUrl.trim()
    if (!envUrl) {
      setError('Please enter your Dataverse environment URL first.')
      return
    }

    const cleanUrl = envUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '')

    setError(null)
    setConnecting(true)

    try {
      const { instance, ready } = getMsalInstance()
      await ready

      // Check if already signed in — try silent token acquisition first
      const accounts = instance.getAllAccounts()
      if (accounts.length > 0) {
        try {
          const silentResult = await instance.acquireTokenSilent({
            scopes: [`https://${cleanUrl}/user_impersonation`],
            account: accounts[0],
          })
          const token = silentResult.accessToken
          setAccessToken(token)
          setSignedInUser(silentResult.account?.username || 'Microsoft account')

          const response = await listDataverseEntities(cleanUrl, token)
          if (response.entities) {
            setEntities(response.entities)
            sessionStorage.setItem('db_type', 'dataverse')
            sessionStorage.setItem('dv_environment_url', cleanUrl)
            sessionStorage.setItem('dv_access_token', token)
          } else {
            setError(response.error || 'Failed to list entities')
          }
          return
        } catch {
          // Silent failed, fall through to redirect
        }
      }

      // Save env URL before redirect (page will reload)
      sessionStorage.setItem('dv_pending_env_url', cleanUrl)

      // Use redirect flow instead of popup (more reliable across browsers)
      await instance.acquireTokenRedirect({
        scopes: [`https://${cleanUrl}/user_impersonation`],
        prompt: 'select_account',
      })
      // Page will redirect — code below won't execute
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
    sessionStorage.setItem('selected_databases', JSON.stringify(selectedEntities))
    window.location.href = '/extract'
  }

  return (
    <div className="max-w-md mx-auto animate-fadeIn">
      <div className="p-6 glass-panel rounded-2xl">
        <div className="space-y-4">
          {/* Environment URL Field */}
          <div>
            <label htmlFor="environmentUrl" className="block text-sm font-medium text-slate-300 mb-1">
              Dataverse Environment URL
            </label>
            <input
              type="text"
              id="environmentUrl"
              value={environmentUrl}
              onChange={(e) => setEnvironmentUrl(e.target.value)}
              placeholder="org.crm.dynamics.com"
              className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500 transition-all text-slate-200"
            />
            <p className="mt-1 text-xs text-slate-500">
              e.g. yourorg.crm.dynamics.com (without https://)
            </p>
          </div>

          {/* Auth Status */}
          {!signedInUser ? (
            <div className="space-y-3">
              <div className="p-3 bg-amber-900/40 border border-amber-500/30 rounded-lg backdrop-blur-sm">
                <p className="text-sm text-amber-200">
                  Sign in with your Microsoft account to access Dataverse. Your account must have read access to the environment.
                </p>
              </div>
              <button
                type="button"
                onClick={handleSignIn}
                disabled={connecting || !environmentUrl.trim()}
                className="w-full py-2.5 px-4 bg-slate-800 border border-slate-700 text-slate-200 rounded-lg hover:bg-slate-700 hover:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium flex items-center justify-center gap-3 shadow-[0_0_10px_rgba(0,0,0,0.2)]"
              >
                {connecting ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-400" />
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

      {/* Entity Picker (appears after successful connection) */}
      {entities && (
        <div className="mt-6 p-6 glass-panel rounded-2xl animate-fadeIn">
          <div className="mb-4 p-3 bg-emerald-900/40 border border-emerald-500/30 text-emerald-200 rounded-lg backdrop-blur-sm text-sm">
            Connected to: {environmentUrl.trim().replace(/^https?:\/\//, '')}
          </div>

          {entities.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-4">
              No entities found in this environment.
            </p>
          ) : (
            <>
              <DatabasePicker
                databases={entities}
                onSelect={setSelectedEntities}
                selectedDatabases={selectedEntities}
                label="entities"
              />
              <button
                onClick={handleProceed}
                disabled={selectedEntities.length === 0}
                className="mt-6 w-full py-2.5 px-4 bg-gradient-to-r from-purple-500 to-purple-600 text-white text-center rounded-lg shadow-[0_0_15px_rgba(168,85,247,0.5)] border border-white/10 hover:from-purple-400 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-medium"
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
