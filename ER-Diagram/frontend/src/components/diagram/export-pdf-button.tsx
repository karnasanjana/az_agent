'use client'

interface ExportPdfButtonProps {
  onExport: () => void
  isExporting: boolean
}

/**
 * Export PDF button - presentational component for the diagram header.
 *
 * Shows loading state during PDF generation and prevents double-clicks.
 * Parent page owns the export logic and passes onExport callback.
 */
export function ExportPdfButton({ onExport, isExporting }: ExportPdfButtonProps) {
  return (
    <button
      onClick={onExport}
      disabled={isExporting}
      className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {isExporting ? 'Generating PDF...' : 'Export PDF'}
    </button>
  )
}
