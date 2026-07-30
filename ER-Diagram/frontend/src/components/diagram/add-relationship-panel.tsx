'use client'

import { useState, useMemo, useRef, useEffect } from 'react'
import { Panel } from '@xyflow/react'
import type { ManualRelationship } from '@/types/diagram'

interface TableInfo {
  schema_name: string
  table_name: string
  columns: Array<{ name: string }>
}

interface AddRelationshipPanelProps {
  tables: TableInfo[]
  onAdd: (relationship: ManualRelationship) => void
}

/**
 * Searchable dropdown component for selecting tables/columns.
 */
function SearchableSelect({
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  options: string[]
  value: string
  onChange: (val: string) => void
  placeholder: string
  disabled?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = useMemo(() => {
    if (!search) return options
    const lower = search.toLowerCase()
    return options.filter((o) => o.toLowerCase().includes(lower))
  }, [options, search])

  const displayValue = value || placeholder

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => {
          if (!disabled) {
            setIsOpen(!isOpen)
            setTimeout(() => inputRef.current?.focus(), 50)
          }
        }}
        disabled={disabled}
        className={`w-full text-left px-2 py-1.5 text-sm border border-slate-700 rounded-md bg-slate-900/50 backdrop-blur-sm truncate ${
          disabled ? 'opacity-50 cursor-not-allowed text-slate-500' : 'hover:border-slate-500 cursor-pointer'
        } ${value ? 'text-slate-200' : 'text-slate-500'}`}
      >
        {displayValue}
      </button>

      {isOpen && !disabled && (
        <div className="absolute z-50 mt-1 w-full bg-slate-800 border border-slate-700 rounded-md shadow-lg max-h-[200px] flex flex-col">
          {/* Search input */}
          <div className="p-1.5 border-b border-slate-700 flex-shrink-0">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              className="w-full px-2 py-1 text-sm bg-slate-900/50 text-slate-200 border border-slate-700 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder-slate-500"
            />
          </div>
          {/* Options list */}
          <div className="overflow-y-auto flex-1">
            {filtered.length === 0 ? (
              <div className="px-3 py-2 text-xs text-slate-500">No matches</div>
            ) : (
              filtered.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => {
                    onChange(option)
                    setIsOpen(false)
                    setSearch('')
                  }}
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-slate-700 cursor-pointer truncate ${
                    option === value ? 'bg-indigo-900/30 text-indigo-300 font-medium' : 'text-slate-300'
                  }`}
                >
                  {option}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Collapsible panel for manually adding relationships between tables.
 * Positioned in the top-left of the React Flow canvas.
 */
export function AddRelationshipPanel({ tables, onAdd }: AddRelationshipPanelProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [sourceTable, setSourceTable] = useState('')
  const [sourceColumn, setSourceColumn] = useState('')
  const [targetTable, setTargetTable] = useState('')
  const [targetColumn, setTargetColumn] = useState('')

  const tableOptions = useMemo(
    () => tables.map((t) => `${t.schema_name}.${t.table_name}`),
    [tables]
  )

  const sourceColumns = useMemo(() => {
    if (!sourceTable) return []
    const [schema, ...rest] = sourceTable.split('.')
    const tableName = rest.join('.')
    const table = tables.find(
      (t) => t.schema_name === schema && t.table_name === tableName
    )
    return table?.columns.map((c) => c.name) ?? []
  }, [sourceTable, tables])

  const targetColumns = useMemo(() => {
    if (!targetTable) return []
    const [schema, ...rest] = targetTable.split('.')
    const tableName = rest.join('.')
    const table = tables.find(
      (t) => t.schema_name === schema && t.table_name === tableName
    )
    return table?.columns.map((c) => c.name) ?? []
  }, [targetTable, tables])

  const isValid =
    sourceTable !== '' &&
    sourceColumn !== '' &&
    targetTable !== '' &&
    targetColumn !== '' &&
    !(sourceTable === targetTable && sourceColumn === targetColumn)

  const handleAdd = () => {
    if (!isValid) return

    const [sourceSchema, ...sourceRest] = sourceTable.split('.')
    const sourceTableName = sourceRest.join('.')
    const [targetSchema, ...targetRest] = targetTable.split('.')
    const targetTableName = targetRest.join('.')

    const relationship: ManualRelationship = {
      id: `manual_${sourceTable}.${sourceColumn}_${targetTable}.${targetColumn}_${Date.now()}`,
      source_database: sourceSchema,
      source_table: sourceTableName,
      source_column: sourceColumn,
      target_database: targetSchema,
      target_table: targetTableName,
      target_column: targetColumn,
    }

    onAdd(relationship)
    setSourceTable('')
    setSourceColumn('')
    setTargetTable('')
    setTargetColumn('')
    setIsOpen(false)
  }

  const handleCancel = () => {
    setSourceTable('')
    setSourceColumn('')
    setTargetTable('')
    setTargetColumn('')
    setIsOpen(false)
  }

  if (!isOpen) {
    return (
      <Panel position="top-left" className="!m-2">
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-1.5 px-3 py-2 bg-indigo-600 text-white text-sm font-medium border border-indigo-500/50 rounded-lg shadow-[0_0_10px_rgba(79,70,229,0.5)] hover:bg-indigo-500 transition-colors cursor-pointer"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Add Relationship
        </button>
      </Panel>
    )
  }

  return (
    <Panel position="top-left" className="!m-2">
      <div className="glass-panel bg-slate-900/80 rounded-xl shadow-[0_5px_20px_rgba(0,0,0,0.5)] border border-slate-700/80 p-4 w-80">
        <h3 className="text-sm font-bold text-slate-200 mb-3">Add Manual Relationship</h3>

        {/* Source Table */}
        <label className="block text-xs font-medium text-slate-400 mb-1">Source Table</label>
        <div className="mb-2">
          <SearchableSelect
            options={tableOptions}
            value={sourceTable}
            onChange={(val) => { setSourceTable(val); setSourceColumn('') }}
            placeholder="Search tables..."
          />
        </div>

        {/* Source Column */}
        <label className="block text-xs font-medium text-slate-400 mb-1">Source Column</label>
        <div className="mb-3">
          <SearchableSelect
            options={sourceColumns}
            value={sourceColumn}
            onChange={setSourceColumn}
            placeholder="Search columns..."
            disabled={!sourceTable}
          />
        </div>

        {/* Divider with arrow */}
        <div className="flex items-center justify-center mb-3 text-slate-500">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <polyline points="19 12 12 19 5 12" />
          </svg>
        </div>

        {/* Target Table */}
        <label className="block text-xs font-medium text-slate-400 mb-1">Target Table</label>
        <div className="mb-2">
          <SearchableSelect
            options={tableOptions}
            value={targetTable}
            onChange={(val) => { setTargetTable(val); setTargetColumn('') }}
            placeholder="Search tables..."
          />
        </div>

        {/* Target Column */}
        <label className="block text-xs font-medium text-slate-400 mb-1">Target Column</label>
        <div className="mb-4">
          <SearchableSelect
            options={targetColumns}
            value={targetColumn}
            onChange={setTargetColumn}
            placeholder="Search columns..."
            disabled={!targetTable}
          />
        </div>

        {/* Buttons */}
        <div className="flex gap-2">
          <button
            onClick={handleAdd}
            disabled={!isValid}
            className="flex-1 px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white border border-indigo-500/50 rounded-lg shadow-sm hover:bg-indigo-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            Add
          </button>
          <button
            onClick={handleCancel}
            className="flex-1 px-3 py-1.5 text-sm font-medium bg-slate-800 border border-slate-700 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors cursor-pointer"
          >
            Cancel
          </button>
        </div>
      </div>
    </Panel>
  )
}
