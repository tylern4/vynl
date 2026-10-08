import type { AlbumSource } from '../types'

/** Small provenance badge for search results / album metadata. */
export function SourceBadge({ source }: { source: AlbumSource }) {
  return (
    <span className={`source-badge source-${source}`}>
      {source === 'deezer' ? 'Deezer' : 'MusicBrainz'}
    </span>
  )
}
