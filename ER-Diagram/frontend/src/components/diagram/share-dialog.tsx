'use client'

import { useState, useEffect } from 'react'

interface ShareSettings {
  showRelationships: boolean
  shareNote: string
}

interface ShareDialogProps {
  isOpen: boolean
  onClose: () => void
  shareToken: string | null
  diagramName: string
  shareSettings?: ShareSettings
  onShare: () => Promise<string>
  onUnshare: () => Promise<void>
  onUpdateSettings: (settings: ShareSettings) => Promise<void>
}

export function ShareDialog({
  isOpen,
  onClose,
  shareToken,
  diagramName,
  shareSettings,
  onShare,
  onUnshare,
  onUpdateSettings,
}: ShareDialogProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [copied, setCopied] = useState(false)
  const [currentToken, setCurrentToken] = useState(shareToken)
  const [showRelationships, setShowRelationships] = useState(shareSettings?.showRelationships ?? false)
  const [shareNote, setShareNote] = useState(shareSettings?.shareNote ?? '')
  const [settingsChanged, setSettingsChanged] = useState(false)

  // Sync state when props change
  useEffect(() => {
    setCurrentToken(shareToken)
  }, [shareToken])

  useEffect(() => {
    setShowRelationships(shareSettings?.showRelationships ?? false)
    setShareNote(shareSettings?.shareNote ?? '')
    setSettingsChanged(false)
  }, [shareSettings])

  if (!isOpen) return null

  const shareUrl = currentToken
    ? `${window.location.origin}/shared/${currentToken}`
    : null

  const handleShare = async () => {
    setIsLoading(true)
    try {
      const token = await onShare()
      setCurrentToken(token)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to share')
    } finally {
      setIsLoading(false)
    }
  }

  const handleUnshare = async () => {
    setIsLoading(true)
    try {
      await onUnshare()
      setCurrentToken(null)
      setShowRelationships(false)
      setShareNote('')
      setSettingsChanged(false)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to unshare')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopy = async () => {
    if (shareUrl) {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleToggleRelationships = (checked: boolean) => {
    setShowRelationships(checked)
    setSettingsChanged(true)
  }

  const handleNoteChange = (value: string) => {
    setShareNote(value)
    setSettingsChanged(true)
  }

  const handleSaveSettings = async () => {
    setIsSaving(true)
    try {
      await onUpdateSettings({ showRelationships, shareNote })
      setSettingsChanged(false)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save settings')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/70 z-50 backdrop-blur-md" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="glass-panel bg-slate-900/95 rounded-2xl shadow-2xl w-full max-w-md border border-slate-700 p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-lg font-bold text-slate-200">Share Diagram</h2>
            <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <p className="text-sm text-slate-400 mb-5">
            {currentToken
              ? `"${diagramName}" is shared. Anyone with the link can view it (read-only, no credentials exposed).`
              : `Generate a read-only link for "${diagramName}". No login required to view.`}
          </p>

          {currentToken && shareUrl ? (
            <div className="space-y-5">
              {/* Share URL */}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={shareUrl}
                  readOnly
                  className="flex-1 px-3 py-2.5 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 font-mono truncate"
                />
                <button
                  onClick={handleCopy}
                  className="px-4 py-2.5 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)] transition-all font-medium whitespace-nowrap"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>

              {/* Build a pipeline from this reviewed schema — the token IS the
                  catalog source id, passed straight into the embedded builder. */}
              <a
                href={`/pipelines?token=${encodeURIComponent(currentToken)}`}
                className="flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm bg-emerald-600 border border-emerald-500/50 text-white rounded-lg hover:bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)] transition-all font-medium"
              >
                🔧 Build pipeline from this schema →
              </a>

              {/* Display Settings */}
              <div className="border border-slate-700/50 rounded-xl p-4 space-y-4 bg-slate-800/20">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Viewer Settings</h3>

                {/* Show Relationships checkbox */}
                <label className="flex items-start gap-3 cursor-pointer group">
                  <div className="pt-0.5">
                    <input
                      type="checkbox"
                      checked={showRelationships}
                      onChange={(e) => handleToggleRelationships(e.target.checked)}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-indigo-500 focus:ring-indigo-500/30 focus:ring-offset-0 cursor-pointer"
                    />
                  </div>
                  <div>
                    <span className="text-sm text-slate-300 group-hover:text-slate-200 transition-colors">Show relationships</span>
                    <p className="text-[11px] text-slate-500 mt-0.5">Display foreign key connection lines between tables</p>
                  </div>
                </label>

                {/* Share Note */}
                <div>
                  <label className="block text-sm text-slate-300 mb-1.5">Note for viewers</label>
                  <textarea
                    value={shareNote}
                    onChange={(e) => handleNoteChange(e.target.value)}
                    placeholder="Add context for whoever views this diagram..."
                    rows={3}
                    maxLength={500}
                    className="w-full px-3 py-2 text-sm bg-slate-800/60 border border-slate-700/60 rounded-lg text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-colors resize-none"
                  />
                  <p className="text-[10px] text-slate-600 mt-1 text-right">{shareNote.length}/500</p>
                </div>

                {/* Save button */}
                {settingsChanged && (
                  <button
                    onClick={handleSaveSettings}
                    disabled={isSaving}
                    className="w-full px-4 py-2 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 transition-all font-medium disabled:opacity-50"
                  >
                    {isSaving ? 'Saving...' : 'Save Settings'}
                  </button>
                )}
              </div>

              {/* Unshare */}
              <button
                onClick={handleUnshare}
                disabled={isLoading}
                className="w-full px-4 py-2.5 text-sm text-red-400 border border-red-500/30 rounded-lg hover:bg-red-900/20 transition-colors disabled:opacity-50"
              >
                {isLoading ? 'Revoking...' : 'Revoke Link'}
              </button>
            </div>
          ) : (
            <button
              onClick={handleShare}
              disabled={isLoading}
              className="w-full px-4 py-3 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-xl hover:bg-indigo-500 shadow-[0_0_15px_rgba(79,70,229,0.4)] transition-all font-medium disabled:opacity-50"
            >
              {isLoading ? 'Generating...' : 'Generate Share Link'}
            </button>
          )}
        </div>
      </div>
    </>
  )
}
