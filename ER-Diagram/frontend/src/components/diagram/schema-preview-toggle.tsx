'use client'

interface SchemaPreviewToggleProps {
  activeView: 'before' | 'after'
  onToggle: (view: 'before' | 'after') => void
  appliedCount: number
  totalCount: number
  onConfirm: () => void
  onDiscard: () => void
}

export function SchemaPreviewToggle({
  activeView,
  onToggle,
  appliedCount,
  totalCount,
  onConfirm,
  onDiscard,
}: SchemaPreviewToggleProps) {
  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 bg-white border border-gray-300 rounded-full shadow-lg px-2 py-1.5">
      {/* Toggle buttons */}
      <div className="flex rounded-full bg-gray-100 p-0.5">
        <button
          onClick={() => onToggle('before')}
          className={`px-3 py-1 text-xs font-medium rounded-full transition-all ${
            activeView === 'before'
              ? 'bg-white text-gray-900 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Before
        </button>
        <button
          onClick={() => onToggle('after')}
          className={`px-3 py-1 text-xs font-medium rounded-full transition-all ${
            activeView === 'after'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          After
        </button>
      </div>

      {/* Applied count */}
      <span className="text-[10px] text-gray-500 border-l border-gray-200 pl-3">
        {appliedCount}/{totalCount} applied
      </span>

      {/* Action buttons */}
      {appliedCount > 0 && (
        <>
          <button
            onClick={onConfirm}
            className="px-3 py-1 text-xs font-medium bg-green-600 text-white rounded-full hover:bg-green-700 transition-colors"
          >
            Confirm Changes
          </button>
          <button
            onClick={onDiscard}
            className="px-2 py-1 text-xs text-gray-500 hover:text-red-600 transition-colors"
            title="Discard all changes"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </>
      )}
    </div>
  )
}
