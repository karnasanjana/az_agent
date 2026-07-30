'use client'

import { useState, useEffect, useRef } from 'react'

interface SaveDialogProps {
  isOpen: boolean
  onClose: () => void
  onSave: (name: string) => Promise<void>
  defaultName: string
  isSaving: boolean
}

/**
 * Modal dialog for naming and saving a diagram.
 * Pre-fills with database name, auto-focuses input on open.
 */
export function SaveDialog({
  isOpen,
  onClose,
  onSave,
  defaultName,
  isSaving,
}: SaveDialogProps) {
  const [name, setName] = useState(defaultName)
  const inputRef = useRef<HTMLInputElement>(null)

  // Reset name and focus input when dialog opens
  useEffect(() => {
    if (isOpen) {
      setName(defaultName)
      // Small delay to ensure DOM is rendered before focusing
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen, defaultName])

  if (!isOpen) return null

  const handleSave = async () => {
    const trimmed = name.trim()
    if (!trimmed) return
    await onSave(trimmed)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
        <h2 className="text-lg font-bold text-gray-900 mb-4">Save Diagram</h2>

        <label className="block text-sm font-medium text-gray-700 mb-1">
          Diagram Name
        </label>
        <input
          ref={inputRef}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !isSaving) handleSave()
          }}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 mb-4"
          placeholder="My Diagram"
          disabled={isSaving}
        />

        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isSaving}
            className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !name.trim()}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
