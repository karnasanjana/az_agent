'use client'

import { useState, useMemo, useRef, useEffect } from 'react'

export interface ToolbarItem {
  id: string
  label: string
  icon: React.ReactNode
  onClick: () => void
  badge?: string | number
  active?: boolean
  disabled?: boolean
  group?: string
}

interface ToolbarProps {
  items: ToolbarItem[]
}

const GROUP_ORDER = ['data', 'view', 'ai', 'collaborate', 'navigate']

const GROUP_LABELS: Record<string, string> = {
  data: 'Data',
  view: 'View',
  ai: 'AI Tools',
  collaborate: 'Collaborate',
  navigate: 'Navigate',
}

const GROUP_ICONS: Record<string, React.ReactNode> = {
  data: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" /><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  ),
  view: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
    </svg>
  ),
  ai: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
    </svg>
  ),
  collaborate: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /><path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  navigate: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><line x1="9" y1="3" x2="9" y2="21" />
    </svg>
  ),
}

export function Toolbar({ items }: ToolbarProps) {
  const [expanded, setExpanded] = useState(false)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set(GROUP_ORDER))
  const searchRef = useRef<HTMLInputElement>(null)

  // Auto-expand sidebar when user starts searching
  useEffect(() => {
    if (search && !expanded) setExpanded(true)
  }, [search, expanded])

  // Group items
  const grouped = useMemo(() => {
    const groups: Record<string, ToolbarItem[]> = {}
    for (const item of items) {
      const g = item.group || 'navigate'
      if (!groups[g]) groups[g] = []
      groups[g].push(item)
    }
    return groups
  }, [items])

  // Filter by search
  const filteredGroups = useMemo(() => {
    if (!search.trim()) return grouped
    const q = search.toLowerCase()
    const result: Record<string, ToolbarItem[]> = {}
    for (const [group, groupItems] of Object.entries(grouped)) {
      const matched = groupItems.filter(
        (item) =>
          item.label.toLowerCase().includes(q) ||
          group.toLowerCase().includes(q) ||
          (GROUP_LABELS[group] || '').toLowerCase().includes(q)
      )
      if (matched.length > 0) result[group] = matched
    }
    return result
  }, [grouped, search])

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const totalResults = Object.values(filteredGroups).reduce((sum, g) => sum + g.length, 0)

  return (
    <div
      className={`h-full flex flex-col bg-slate-900/40 backdrop-blur-xl border-r border-slate-700/80 transition-all duration-300 flex-shrink-0 relative z-20 shadow-2xl ${
        expanded ? 'w-60' : 'w-16'
      }`}
    >
      {/* Toggle arrow — centered when collapsed, right-aligned when expanded */}
      <button
        onClick={() => {
          setExpanded((prev) => !prev)
          if (expanded) setSearch('')
        }}
        className={`absolute top-2 z-10 w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800/60 border border-slate-700/50 hover:bg-slate-700/80 hover:border-slate-600/60 transition-all ${
          expanded ? 'right-2' : 'left-1/2 -translate-x-1/2'
        }`}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`text-slate-400 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      {/* Search bar — collapsed: icon only, expanded: full input */}
      <div className="pt-10 px-2 pb-2 flex-shrink-0">
        {expanded ? (
          <div className="relative animate-fadeIn">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              ref={searchRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tools..."
              className="w-full pl-9 pr-8 py-2 text-sm bg-slate-800/60 border border-slate-700/60 rounded-lg text-slate-300 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-colors"
            />
            {search && (
              <button
                onClick={() => { setSearch(''); searchRef.current?.focus() }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-400 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
        ) : (
          <button
            onClick={() => { setExpanded(true); setTimeout(() => searchRef.current?.focus(), 100) }}
            onMouseEnter={() => setHoveredId('__search')}
            onMouseLeave={() => setHoveredId(null)}
            className="relative w-full flex items-center justify-center py-2.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800/40 rounded-lg transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            {hoveredId === '__search' && (
              <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2.5 py-1.5 bg-slate-800 border border-slate-700 text-slate-200 text-xs font-medium rounded-lg whitespace-nowrap z-50 shadow-xl pointer-events-none animate-fadeIn">
                Search
              </div>
            )}
          </button>
        )}
      </div>

      {/* Grouped tool items */}
      <div className="flex-1 flex flex-col pb-4 overflow-y-auto scrollbar-thin">
        {search && totalResults === 0 && (
          <div className="px-4 py-6 text-center">
            <p className="text-xs text-slate-600">No tools found</p>
          </div>
        )}

        {GROUP_ORDER.filter((g) => filteredGroups[g]).map((group) => {
          const groupItems = filteredGroups[group]
          if (!groupItems) return null
          const isCollapsed = collapsedGroups.has(group) && !search

          return (
            <div key={group} className="mb-1">
              {/* Group header */}
              {expanded ? (
                <button
                  onClick={() => toggleGroup(group)}
                  className="w-full flex items-center gap-2 px-4 py-2 text-[10px] tracking-widest text-slate-400 font-semibold uppercase hover:text-slate-300 transition-colors"
                >
                  <span className="text-slate-600">{GROUP_ICONS[group]}</span>
                  <span className="flex-1 text-left">{GROUP_LABELS[group] || group}</span>
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`text-slate-600 transition-transform duration-200 ${isCollapsed ? '-rotate-90' : ''}`}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
              ) : (
                /* Collapsed: show group icon centered with tooltip */
                <div className="relative">
                  <button
                    onClick={() => { setExpanded(true); toggleGroup(group) }}
                    onMouseEnter={() => setHoveredId(`__group_${group}`)}
                    onMouseLeave={() => setHoveredId(null)}
                    className="w-full flex items-center justify-center py-3 text-slate-500 hover:text-slate-300 hover:bg-slate-800/40 transition-colors"
                  >
                    <span className="w-5 h-5 flex items-center justify-center">{GROUP_ICONS[group]}</span>
                  </button>
                  {hoveredId === `__group_${group}` && (
                    <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2.5 py-1.5 bg-slate-800 border border-slate-700 text-slate-200 text-xs font-medium rounded-lg whitespace-nowrap z-50 shadow-xl pointer-events-none animate-fadeIn">
                      {GROUP_LABELS[group] || group}
                    </div>
                  )}
                </div>
              )}

              {/* Group items */}
              {!isCollapsed && (
                <div className="space-y-0.5">
                  {groupItems.map((item) => (
                    <div key={item.id} className="relative">
                      <button
                        onClick={item.onClick}
                        disabled={item.disabled}
                        onMouseEnter={() => setHoveredId(item.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        className={`relative w-full flex items-center gap-3 px-4 py-2.5 transition-all duration-200 ${
                          item.active
                            ? 'bg-gradient-to-r from-indigo-900/40 to-transparent text-indigo-300 border-l-[3px] border-indigo-500 shadow-[inset_0_0_20px_rgba(79,70,229,0.15)]'
                            : 'text-slate-300 hover:bg-slate-800/40 hover:text-slate-100 border-l-[3px] border-transparent'
                        } ${item.disabled ? 'opacity-40 cursor-not-allowed' : 'group'}`}
                      >
                        <span
                          className={`w-5 h-5 flex-shrink-0 flex items-center justify-center transition-transform duration-200 ${
                            item.active
                              ? 'text-indigo-400'
                              : 'text-slate-500 group-hover:text-slate-300 group-hover:scale-110'
                          }`}
                        >
                          {item.icon}
                        </span>
                        {expanded && (
                          <span className="truncate text-[13px] font-medium">{item.label}</span>
                        )}
                        {item.badge && (
                          <span
                            className={`absolute ${expanded ? 'right-2' : 'top-0.5 right-0.5'} text-[10px] font-bold px-1 min-w-[16px] text-center rounded-full ${
                              item.active
                                ? 'bg-indigo-900/80 text-indigo-300'
                                : 'bg-slate-800 text-slate-500'
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                      </button>
                      {/* Tooltip — only when collapsed */}
                      {!expanded && hoveredId === item.id && (
                        <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2.5 py-1.5 bg-slate-800 border border-slate-700 text-slate-200 text-xs font-medium rounded-lg whitespace-nowrap z-50 shadow-xl pointer-events-none animate-fadeIn">
                          {item.label}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
