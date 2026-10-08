export type Role = 'admin' | 'user' | 'read_only'

export type UserStatus = 'pending' | 'active' | 'denied'

export interface User {
  id: number
  name: string
  email: string
  role: Role
  status: UserStatus
}

export interface UserAdmin extends User {
  created_at: string
}

export interface RegisterResult {
  user: User
  access_token: string | null
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: User
}

export type AlbumSource = 'deezer' | 'musicbrainz'

export type AlbumSort = 'added' | 'title' | 'artist' | 'year' | 'played'

export interface SearchResult {
  source: AlbumSource
  external_id: string
  title: string
  artist: string
  year: number | null
  track_count: number | null
  cover_url: string | null
  label: string | null
}

export interface Track {
  id: number
  position: number
  title: string
  duration_seconds: number | null
}

export interface Album {
  id: number
  title: string
  artist: string
  year: number | null
  label: string | null
  country: string | null
  source: AlbumSource
  external_id: string
  cover_url: string | null
  track_count: number
  favorite: boolean
  note: string | null
  last_played_at: string | null
  tags: string[]
  created_at: string
  /** Only present on `GET /api/albums/{id}` (detail). */
  tracks?: Track[]
}

export interface AlbumImport {
  source: AlbumSource
  external_id: string
}

/** One dry-run track from `POST /albums/preview` (issue #13). */
export interface TrackPreview {
  position: number
  title: string
  duration_seconds: number | null
}

/** Which provider fed each part of an assembled (dry-run) album (#13). */
export interface AlbumSourceBreakdown {
  metadata_source: string | null
  tracklist_source: string | null
  artwork_source: string | null
}

/**
 * Dry-run of what importing `{source, external_id}` would persist (#13).
 * Same shape the import would create, plus per-source provenance.
 */
export interface AlbumPreview {
  source: AlbumSource
  external_id: string
  title: string
  artist: string
  year: number | null
  label: string | null
  country: string | null
  cover_url: string | null
  track_count: number
  tracks: TrackPreview[]
  source_breakdown: AlbumSourceBreakdown
  tracklists_by_source: Record<string, TrackPreview[]>
}

export interface AlbumUpdate {
  favorite?: boolean
  note?: string | null
  year?: number | null
  label?: string | null
}

export interface AlbumListParams {
  q?: string
  tag?: string
  favorite?: boolean
  sort?: AlbumSort
  limit?: number
  offset?: number
}

export interface Tag {
  id: number
  name: string
  album_count: number
}

export interface Play {
  id: number
  played_at: string
}

export interface TrackSearchAlbum {
  id: number
  title: string
  artist: string
  year: number | null
  cover_url: string | null
}

export interface TrackSearchResult {
  id: number
  title: string
  duration_seconds: number | null
  position: number
  album: TrackSearchAlbum
}

export type RecommendationMode = 'dusty' | 'random'

export interface Recommendation {
  album: Album
  reason: string
  days_since_played: number | null
}

export interface RecommendationParams {
  mode?: RecommendationMode
  tag?: string
  n?: number
}
