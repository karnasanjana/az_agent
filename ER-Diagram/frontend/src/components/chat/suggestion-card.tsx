'use client'

import type { Suggestion } from '@/types/chat'
import { categorizeSuggestionChanges } from '@/lib/schema-diff'

interface SuggestionCardProps {
  suggestion: Suggestion
  onAccept: (suggestion: Suggestion) => void
  onSkip: (suggestion: Suggestion) => void
  onPreview: (suggestion: Suggestion) => void
  onClearPreview: () => void
}

export default function SuggestionCard({
  suggestion,
  onAccept,
  onSkip,
  onPreview,
  onClearPreview,
}: SuggestionCardProps) {
  const changes = categorizeSuggestionChanges(suggestion)
  const isResolved = suggestion.status === 'accepted' || suggestion.status === 'skipped'

  return (
    <div
      className={`border rounded-lg p-3 text-sm ${
        suggestion.status === 'accepted'
          ? 'border-green-300 bg-green-50'
          : suggestion.status === 'skipped'
          ? 'border-gray-200 bg-gray-50 opacity-60'
          : 'border-blue-200 bg-blue-50'
      }`}
      onMouseEnter={() => !isResolved && onPreview(suggestion)}
      onMouseLeave={() => !isResolved && onClearPreview()}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h4 className="font-medium text-gray-900">{suggestion.title}</h4>
        {suggestion.status === 'accepted' && (
          <span className="text-xs px-2 py-0.5 bg-green-200 text-green-800 rounded-full flex-shrink-0">Added to diagram</span>
        )}
        {suggestion.status === 'skipped' && (
          <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-600 rounded-full flex-shrink-0">Skipped</span>
        )}
      </div>

      {/* Change summary */}
      <div className="space-y-1 mb-3">
        {changes.removedTables.map((t) => (
          <div key={`rm-${t}`} className="flex items-center gap-1.5 text-red-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">-</span>
            <span>Remove table <code className="bg-red-100 px-1 rounded">{t}</code></span>
          </div>
        ))}
        {changes.addedTables.map((t) => (
          <div key={`add-${t}`} className="flex items-center gap-1.5 text-green-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">+</span>
            <span>Add table <code className="bg-green-100 px-1 rounded">{t}</code></span>
          </div>
        ))}
        {changes.movedColumns.map((m) => (
          <div key={`mv-${m.column}`} className="flex items-center gap-1.5 text-amber-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">&rarr;</span>
            <span>
              Move <code className="bg-amber-100 px-1 rounded">{m.column}</code> from{' '}
              <code className="bg-red-100 px-1 rounded">{m.from}</code> to{' '}
              <code className="bg-green-100 px-1 rounded">{m.to}</code>
            </span>
          </div>
        ))}
        {changes.addedColumns.map((c) => (
          <div key={`ac-${c.table}-${c.column}`} className="flex items-center gap-1.5 text-green-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">+</span>
            <span>
              Add column <code className="bg-green-100 px-1 rounded">{c.column}</code> to{' '}
              <code className="bg-green-100 px-1 rounded">{c.table}</code>
            </span>
          </div>
        ))}
        {changes.removedColumns.map((c) => (
          <div key={`rc-${c.table}-${c.column}`} className="flex items-center gap-1.5 text-red-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">-</span>
            <span>
              Remove column <code className="bg-red-100 px-1 rounded">{c.column}</code> from{' '}
              <code className="bg-red-100 px-1 rounded">{c.table}</code>
            </span>
          </div>
        ))}
        {changes.addedRelationships.map((r) => (
          <div key={`ar-${r.source}-${r.target}`} className="flex items-center gap-1.5 text-green-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">+</span>
            <span>
              Add relationship <code className="bg-green-100 px-1 rounded">{r.source}</code> &rarr;{' '}
              <code className="bg-green-100 px-1 rounded">{r.target}</code>
            </span>
          </div>
        ))}
        {changes.removedRelationships.map((name) => (
          <div key={`rr-${name}`} className="flex items-center gap-1.5 text-red-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">-</span>
            <span>Remove relationship <code className="bg-red-100 px-1 rounded">{name}</code></span>
          </div>
        ))}
        {changes.modifiedTables.map((t) => (
          <div key={`mod-${t}`} className="flex items-center gap-1.5 text-amber-700">
            <span className="w-4 h-4 flex items-center justify-center text-xs font-bold">~</span>
            <span>Modify table <code className="bg-amber-100 px-1 rounded">{t}</code></span>
          </div>
        ))}
      </div>

      {/* Action buttons */}
      {!isResolved && (
        <div className="flex gap-2">
          <button
            onClick={() => onAccept(suggestion)}
            className="flex-1 px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
          >
            Add to diagram
          </button>
          <button
            onClick={() => onSkip(suggestion)}
            className="flex-1 px-3 py-1.5 text-xs font-medium border border-gray-300 text-gray-600 rounded-md hover:bg-gray-100 transition-colors"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  )
}
