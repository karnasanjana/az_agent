'use client'

import { useSession } from 'next-auth/react'
import { usePathname } from 'next/navigation'

/**
 * Auth gate - shows login page if user is not authenticated.
 * Allows /login and /api/auth routes to pass through.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession()
  const pathname = usePathname()

  // ponytail: local UI preview bypass — remove NEXT_PUBLIC_SKIP_AUTH to restore Google gate
  if (process.env.NEXT_PUBLIC_SKIP_AUTH === 'true') {
    return <>{children}</>
  }

  // Allow login page, auth API routes, and shared diagram pages through
  if (pathname === '/login' || pathname.startsWith('/api/auth') || pathname.startsWith('/shared/')) {
    return <>{children}</>
  }

  // Show loading while checking auth
  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-gradient-brand flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-indigo-400 border-t-transparent mx-auto mb-4" />
          <p className="text-slate-400 text-sm">Loading...</p>
        </div>
      </div>
    )
  }

  // Refresh token expired or revoked — force re-login
  if ((session as any)?.error === 'RefreshTokenError') {
    return <LoginPrompt message="Your session has expired. Please sign in again." />
  }

  // Not authenticated — show login page inline
  if (!session?.user) {
    return <LoginPrompt />
  }

  // Authenticated — render the app
  return <>{children}</>
}

function LoginPrompt({ message }: { message?: string } = {}) {
  return (
    <main className="min-h-screen bg-gradient-brand flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-10 max-w-md w-full text-center border border-slate-200/50">
        {/* Logo */}
        <div className="mb-8">
          <div className="mx-auto w-16 h-16 rounded-2xl bg-indigo-600 flex items-center justify-center mb-5 shadow-lg shadow-indigo-600/30">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">DataLake Orchestrator</h1>
          <p className="mt-2 text-slate-500 text-sm">
            Connect, visualize, and optimize your data infrastructure
          </p>
        </div>

        {/* Features */}
        <div className="text-left mb-8 space-y-3">
          <div className="flex items-start gap-3">
            <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center mt-0.5 flex-shrink-0">
              <svg className="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm text-slate-600">Connect to SQL Server & Google BigQuery</p>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center mt-0.5 flex-shrink-0">
              <svg className="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm text-slate-600">AI-powered schema optimization & data queries</p>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center mt-0.5 flex-shrink-0">
              <svg className="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-sm text-slate-600">Interactive ER diagrams with export & sharing</p>
          </div>
        </div>

        {/* Session expired message */}
        {message && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800">
            {message}
          </div>
        )}

        {/* Divider */}
        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center">
            <span className="bg-white px-4 text-xs text-slate-400 uppercase tracking-wider">Sign in to continue</span>
          </div>
        </div>

        {/* Google Sign In Button */}
        <GoogleSignInButton />

        <p className="text-xs text-slate-400 mt-6">
          By signing in, you agree to our Terms of Service
        </p>
      </div>
    </main>
  )
}

function GoogleSignInButton() {
  const { signIn } = require('next-auth/react')

  return (
    <button
      type="button"
      onClick={() => signIn('google', { callbackUrl: '/' })}
      className="w-full flex items-center justify-center gap-3 bg-white border-2 border-slate-200 rounded-xl px-6 py-3.5 text-slate-700 font-medium hover:bg-slate-50 hover:border-slate-300 hover:shadow-md active:scale-[0.98] transition-all"
    >
      <svg className="w-5 h-5" viewBox="0 0 24 24">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
      </svg>
      Sign in with Google
    </button>
  )
}
