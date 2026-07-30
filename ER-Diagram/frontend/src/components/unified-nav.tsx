'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import UserMenu from '@/components/user-menu'

const items = [
  { href: '/', label: 'Connect', icon: 'database' },
  { href: '/diagrams', label: 'Diagrams', icon: 'diagram' },
  { href: '/dictionary', label: 'Dictionary', icon: 'book' },
  { href: '/pipelines', label: 'Pipelines', icon: 'pipeline' },
] as const

function NavIcon({ name }: { name: string }) {
  if (name === 'database') return <svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"/></svg>
  if (name === 'diagram') return <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="6" rx="1"/><rect x="14" y="15" width="7" height="6" rx="1"/><path d="M10 6h3a4 4 0 0 1 4 4v5M7 9v3a6 6 0 0 0 6 6h1"/></svg>
  if (name === 'book') return <svg viewBox="0 0 24 24"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5ZM20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5Z"/></svg>
  return <svg viewBox="0 0 24 24"><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6.2 7.7l4.6 8.5M17.8 7.7l-4.6 8.5"/></svg>
}

export default function UnifiedNav() {
  const pathname = usePathname()
  if (pathname.startsWith('/login') || pathname.startsWith('/shared/') || pathname === '/diagram' || pathname === '/chat') return null

  return (
    <header className="unified-nav">
      <Link href="/" className="unified-brand" aria-label="ZionAi home">
        <span className="unified-brand-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6.2 7.7l4.6 8.5M17.8 7.7l-4.6 8.5"/></svg></span>
        <span><strong>ZionAi</strong><small>Data architecture studio</small></span>
      </Link>
      <nav aria-label="Primary navigation">
        {items.map((item) => {
          const active = item.href === '/' ? pathname === '/' || pathname === '/extract' : pathname.startsWith(item.href)
          return <Link key={item.href} href={item.href} className={active ? 'active' : ''}><NavIcon name={item.icon}/><span>{item.label}</span></Link>
        })}
      </nav>
      <div className="unified-status"><i/> Systems ready</div>
      <UserMenu />
    </header>
  )
}
