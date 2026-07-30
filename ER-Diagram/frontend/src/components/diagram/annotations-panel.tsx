'use client'

import { useState } from 'react'
import type { Annotation } from '@/types/diagram'
import type { DatabaseSchema } from '@/types/schema'

interface AnnotationsPanelProps {
  isOpen: boolean
  onClose: () => void
  annotations: Annotation[]
  onAdd: (annotation: Omit<Annotation, 'id' | 'created_at' | 'updated_at' | 'created_by'>) => void
  onDelete: (id: string) => void
  onUpdate: (id: string, text: string) => void
  schema: DatabaseSchema | null
  userEmail: string
}

export function AnnotationsPanel({
  isOpen,
  onClose,
  annotations,
  onAdd,
  onDelete,
  onUpdate,
  schema,
  userEmail,
}: AnnotationsPanelProps) {
  const [selectedTable, setSelectedTable] = useState('')
  const [selectedColumn, setSelectedColumn] = useState('')
  const [newText, setNewText] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [filterTable, setFilterTable] = useState('')

  if (!isOpen) return null

  const tables = schema?.tables || []
  const selectedTableObj = tables.find(
    (t) => `${t.schema_name}.${t.table_name}` === selectedTable
  )

  const filteredAnnotations = filterTable
    ? annotations.filter((a) => a.target_table === filterTable)
    : annotations

  const handleAdd = () => {
    if (!selectedTable || !newText.trim()) return
    onAdd({
      target_type: selectedColumn ? 'column' : 'table',
      target_table: selectedTable,
      target_column: selectedColumn || null,
      text: newText.trim(),
    })
    setNewText('')
    setSelectedColumn('')
  }

  const handleSaveEdit = (id: string) => {
    if (editText.trim()) {
      onUpdate(id, editText.trim())
    }
    setEditingId(null)
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/50 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-[420px] z-50 glass-panel bg-slate-900/95 border-l border-slate-700 flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-slate-200">Annotations</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {annotations.length} note{annotations.length !== 1 ? 's' : ''}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Add annotation form */}
        <div className="px-5 py-4 border-b border-slate-800 space-y-3 flex-shrink-0">
          <div className="flex gap-2">
            <select
              value={selectedTable}
              onChange={(e) => {
                setSelectedTable(e.target.value)
                setSelectedColumn('')
              }}
              className="flex-1 px-3 py-2 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              <option value="">Select table...</option>
              {tables.map((t) => (
                <option key={`${t.schema_name}.${t.table_name}`} value={`${t.schema_name}.${t.table_name}`}>
                  {t.schema_name}.{t.table_name}
                </option>
              ))}
            </select>
            {selectedTableObj && (
              <select
                value={selectedColumn}
                onChange={(e) => setSelectedColumn(e.target.value)}
                className="w-36 px-3 py-2 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                <option value="">All columns</option>
                {selectedTableObj.columns.map((c) => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="Add a note..."
              className="flex-1 px-3 py-2 text-sm bg-slate-800/80 border border-slate-700 rounded-lg text-slate-300 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            <button
              onClick={handleAdd}
              disabled={!selectedTable || !newText.trim()}
              className="px-4 py-2 text-sm bg-indigo-600 border border-indigo-500/50 text-white rounded-lg hover:bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)] transition-all disabled:opacity-50 font-medium"
            >
              Add
            </button>
          </div>
        </div>

        {/* Filter */}
        {annotations.length > 0 && (
          <div className="px-5 py-2 border-b border-slate-800 flex-shrink-0">
            <select
              value={filterTable}
              onChange={(e) => setFilterTable(e.target.value)}
              className="w-full px-3 py-1.5 text-sm bg-slate-800/50 border border-slate-700 rounded-lg text-slate-400 focus:outline-none"
            >
              <option value="">All tables</option>
              {[...new Set(annotations.map((a) => a.target_table))].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        )}

        {/* Annotations list */}
        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3">
          {filteredAnnotations.length === 0 && (
            <p className="text-sm text-slate-500 text-center py-8">
              No annotations yet. Select a table and add a note.
            </p>
          )}
          {filteredAnnotations.map((ann) => (
            <div key={ann.id} className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-3 group">
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-1.5">
                  <span className={`inline-block w-2 h-2 rounded-full ${ann.target_type === 'table' ? 'bg-indigo-400' : 'bg-amber-400'}`} />
                  <span className="text-xs font-medium text-slate-300">
                    {ann.target_table}
                    {ann.target_column && <span className="text-slate-500">.{ann.target_column}</span>}
                  </span>
                </div>
                <button
                  onClick={() => onDelete(ann.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-slate-500 hover:text-red-400 transition-all"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
              {editingId === ann.id ? (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit(ann.id)}
                    className="flex-1 px-2 py-1 text-sm bg-slate-900 border border-slate-600 rounded text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
                    autoFocus
                  />
                  <button onClick={() => handleSaveEdit(ann.id)} className="text-xs text-indigo-400 hover:text-indigo-300">Save</button>
                  <button onClick={() => setEditingId(null)} className="text-xs text-slate-500 hover:text-slate-400">Cancel</button>
                </div>
              ) : (
                <p
                  className="text-sm text-slate-400 cursor-pointer hover:text-slate-300 transition-colors"
                  onClick={() => { setEditingId(ann.id); setEditText(ann.text) }}
                >
                  {ann.text}
                </p>
              )}
              <div className="flex items-center gap-2 mt-2 text-[10px] text-slate-600">
                <span>{ann.created_by}</span>
                <span>{new Date(ann.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
