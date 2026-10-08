import type { AlbumSource } from '../types'

const LABELS: Record<AlbumSource, string> = {
  deezer: 'Deezer',
  musicbrainz: 'MusicBrainz',
  manual: 'Manual',
}

/** Small provenance badge for search results / album metadata. */
export function SourceBadge({ source }: { source: AlbumSource }) {
  return <span className={`source-badge source-${source}`}>{LABELS[source]}</span>
}