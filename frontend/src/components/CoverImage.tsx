import { useEffect, useState } from 'react'
import { Disc3 } from 'lucide-react'
import { api } from '../api'

interface CoverImageProps {
  /** Album id for the cached-cover endpoint; omit/null for un-imported search results. */
  albumId?: number | null
  coverUrl?: string | null
  alt: string
  className?: string
}

/**
 * Album artwork with the PLAN §5 fallback chain:
 * cached `GET /api/albums/{id}/cover` (fetched with auth as a blob) →
 * remote `cover_url` → placeholder. Always lazy-loads.
 */
export function CoverImage({ albumId, coverUrl, alt, className }: CoverImageProps) {
  const hasCached = albumId !== null && albumId !== undefined
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [stage, setStage] = useState<0 | 1 | 2>(
    hasCached ? 0 : coverUrl ? 1 : 2,
  )

  // The cover endpoint requires the Bearer token, so fetch it through api.ts.
  useEffect(() => {
    if (!hasCached) return
    let cancelled = false
    api.getCoverBlob(albumId as number).then((blob) => {
      if (!blob || cancelled) return
      setBlobUrl(URL.createObjectURL(blob))
    })
    return () => {
      cancelled = true
    }
  }, [albumId, hasCached])

  // New album / new art → restart the fallback chain.
  useEffect(() => {
    setStage(hasCached ? 0 : coverUrl ? 1 : 2)
    setBlobUrl(null)
  }, [albumId, hasCached, coverUrl])

  // Revoke the object URL when it is replaced or the cover unmounts.
  useEffect(() => {
    if (!blobUrl) return
    return () => URL.revokeObjectURL(blobUrl)
  }, [blobUrl])

  // A freshly fetched cached cover should win over any fallback shown meanwhile.
  useEffect(() => {
    if (blobUrl) setStage(0)
  }, [blobUrl])

  function handleError() {
    setStage((s) => (s === 0 && coverUrl ? 1 : 2))
  }

  const src = stage === 0 ? (blobUrl ?? api.getCoverUrl(albumId as number)) : coverUrl

  if (stage === 2 || !src) {
    return (
      <div
        className={`cover-placeholder ${className ?? ''}`.trim()}
        role="img"
        aria-label={alt}
      >
        <Disc3 size={28} aria-hidden />
        <span>No cover</span>
      </div>
    )
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className={className}
      onError={handleError}
    />
  )
}