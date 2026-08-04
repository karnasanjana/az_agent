import { PublicClientApplication } from '@azure/msal-browser'

// Shared demo app used only as a last resort — it won't have access to your tenant.
export const DEFAULT_MSAL_CLIENT_ID = '2967332b-4aa0-4a9a-89ca-596d6d54a009'

// Resolution order for the Azure AD app (client) id used to sign in for
// Dataverse/SharePoint: build-time env var, then a client id the user entered in
// the connect form (saved in localStorage), then the shared demo app.
export function getMsalClientId(): string {
  const env = process.env.NEXT_PUBLIC_MSAL_CLIENT_ID
  if (env) return env
  if (typeof window !== 'undefined') {
    const stored = localStorage.getItem('msal_client_id')?.trim()
    if (stored) return stored
  }
  return DEFAULT_MSAL_CLIENT_ID
}

let instance: PublicClientApplication | null = null
let initPromise: Promise<void> | null = null
let usedClientId: string | null = null

// Singleton MSAL instance. Recreated if the resolved client id changed (e.g. the
// user just entered their own), so a mid-session change applies on next connect.
export function getMsalInstance(): { instance: PublicClientApplication; ready: Promise<void> } {
  const clientId = getMsalClientId()
  if (!instance || usedClientId !== clientId) {
    usedClientId = clientId
    instance = new PublicClientApplication({
      auth: {
        clientId,
        authority: 'https://login.microsoftonline.com/common',
        redirectUri: window.location.origin,
      },
      cache: { cacheLocation: 'sessionStorage' },
    })
    initPromise = instance.initialize()
  }
  return { instance, ready: initPromise! }
}
