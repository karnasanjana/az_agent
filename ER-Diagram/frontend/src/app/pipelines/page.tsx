'use client'

import { useEffect, useState } from 'react'

// Pipelines tab: embeds the az_agent pipeline builder and passes the current
// diagram's share token as ?catalog_source_id=..., so az_agent grounds the
// pipeline on the schema reviewed here — one place, no token copying.
export default function PipelinesPage() {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token')
    const base = process.env.NEXT_PUBLIC_AZ_AGENT_URL ?? 'http://localhost:8000'
    const params = new URLSearchParams({ embedded: '1' })
    if (token) params.set('catalog_source_id', token)
    setSrc(`${base}/?${params.toString()}`)
  }, [])

  if (!src) return null
  return (
    <div className="pipeline-embed">
      <iframe
        src={src}
        title="Pipeline Builder"
        style={{ width: '100%', height: '100%', border: 'none' }}
      />
    </div>
  )
}
