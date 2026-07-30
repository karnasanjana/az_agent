"use client"

import { useState, useRef, useEffect } from "react"
import { useSession, signIn, signOut } from "next-auth/react"

export default function UserMenu() {
  const { data: session, status } = useSession()
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside)
      return () => document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [isOpen])

  // Close on Escape
  useEffect(() => {
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setIsOpen(false)
    }
    if (isOpen) {
      document.addEventListener("keydown", handleEscape)
      return () => document.removeEventListener("keydown", handleEscape)
    }
  }, [isOpen])

  if (status === "loading") return null

  if (!session?.user) {
    return (
      <button
        onClick={() => signIn('google')}
        className="flex items-center gap-2 px-4 py-2 bg-white/10 border border-white/20 rounded-lg hover:bg-white/20 transition-colors"
      >
        <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0" />
        </svg>
        <span className="text-sm font-medium text-white/90">Sign in</span>
      </button>
    )
  }

  const initials = (session.user.name || "U")
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2)

  return (
    <div className="relative" ref={menuRef}>
      {/* Avatar button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-9 h-9 rounded-full ring-2 ring-white/20 hover:ring-white/40 transition-all overflow-hidden"
        title={session.user.name || "Account"}
      >
        {session.user.image ? (
          <img
            src={session.user.image}
            alt=""
            className="w-9 h-9 rounded-full"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="w-9 h-9 rounded-full bg-indigo-500 flex items-center justify-center text-white text-sm font-semibold">
            {initials}
          </div>
        )}
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 bg-slate-900/95 backdrop-blur-xl rounded-xl shadow-2xl border border-slate-700/80 py-1 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
          {/* User info section */}
          <div className="px-4 py-3 border-b border-slate-700/80">
            <div className="flex items-center gap-3">
              {session.user.image ? (
                <img
                  src={session.user.image}
                  alt=""
                  className="w-10 h-10 rounded-full ring-2 ring-slate-700"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center text-white text-sm font-semibold">
                  {initials}
                </div>
              )}
              <div className="min-w-0">
                <p className="text-sm font-semibold text-slate-100 truncate">
                  {session.user.name}
                </p>
                <p className="text-xs text-slate-400 truncate">
                  {session.user.email}
                </p>
              </div>
            </div>
          </div>

          {/* Navigation links */}
          <div className="py-1">
            <a
              href="/diagrams"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-slate-100 transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
              My Diagrams
            </a>
            <a
              href="/"
              onClick={() => setIsOpen(false)}
              className="flex items-center gap-3 px-4 py-2.5 text-sm text-slate-300 hover:bg-slate-800 hover:text-slate-100 transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-slate-500">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              New Connection
            </a>
          </div>

          {/* Sign out */}
          <div className="border-t border-slate-700/80 py-1">
            <button
              onClick={() => {
                setIsOpen(false)
                signOut({ callbackUrl: "/" })
              }}
              className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-red-400 hover:bg-red-900/30 transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-500">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
