import { signIn } from "@/lib/auth"

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-gradient-brand flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl p-10 max-w-md w-full text-center border border-slate-200/50">
        <div className="mx-auto w-16 h-16 rounded-2xl bg-indigo-600 flex items-center justify-center mb-5 shadow-lg shadow-indigo-600/30">
          <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-slate-900 mb-2">DataLake Orchestrator</h1>
        <p className="text-slate-500 mb-8 text-sm">
          Sign in to visualize and optimize your data infrastructure
        </p>
        <form
          action={async () => {
            "use server"
            await signIn("google", { redirectTo: "/" })
          }}
        >
          <button
            type="submit"
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
        </form>
        <p className="text-xs text-slate-400 mt-6">
          Only Google accounts are supported
        </p>
      </div>
    </main>
  )
}
