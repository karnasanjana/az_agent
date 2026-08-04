'use client'

import { useState } from 'react'

// Optional input to sign in with YOUR Azure AD app instead of the shared demo one,
// for Dataverse/SharePoint. Saved in this browser (localStorage 'msal_client_id')
// and read by getMsalClientId(). Hidden when NEXT_PUBLIC_MSAL_CLIENT_ID is set,
// since the env value wins and a field here would be silently ignored.
export default function ClientIdField() {
  const envSet = !!process.env.NEXT_PUBLIC_MSAL_CLIENT_ID
  const [value, setValue] = useState<string>(() =>
    typeof window !== 'undefined' ? (localStorage.getItem('msal_client_id') || '') : ''
  )
  if (envSet) return null

  const save = (v: string) => {
    setValue(v)
    if (v.trim()) localStorage.setItem('msal_client_id', v.trim())
    else localStorage.removeItem('msal_client_id')
  }

  return (
    <div>
      <label htmlFor="msalClientId" className="block text-sm font-medium text-slate-300 mb-1">
        Azure AD app (client) ID
      </label>
      <input
        id="msalClientId"
        type="text"
        value={value}
        onChange={(e) => save(e.target.value)}
        placeholder="00000000-0000-0000-0000-000000000000"
        className="w-full px-3 py-2 border border-slate-700 bg-slate-900/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500 transition-all text-slate-200"
      />
      <p className="mt-1 text-xs text-slate-500">
        Your Microsoft app with the delegated permissions (admin-consented), saved in this
        browser. Leave blank to use the shared demo app.
      </p>
    </div>
  )
}
