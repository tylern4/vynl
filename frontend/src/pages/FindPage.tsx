import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api, ApiError } from '../api'
import type { Album, Tag, TrackSearchResult } from '../types'
import { AlbumCard } from '../components/AlbumCard'
import { CoverImage } from '../components/CoverImage'
import { formatDuration } from '../format'

const DEBOUNCE_MS = 300

interface SectionState<T> {
  ok: boolean
  items: T[]
  error: string | null
}

/** Run both library searches; one failing never blocks the other. */
async function runLibrarySearch(q: string): Promise<{
  songs: SectionState<TrackSearchResult>
  albums: SectionState<Album>
}> {
  const [songRes, albumRes] = await Promise.all([
    api.searchTracks(q).then(
      (items): SectionState<TrackSearchResult> => ({ ok: true, items, error: null }),
      (err: unknown): SectionState<TrackSearchResult> => ({
        ok: false,
        items: [],
        error: err instanceof ApiError ? err.message : 'Song search failed.',
      }),
    ),
    api.listAlbums({ q }).then(
      (items): SectionState<Album> => ({ ok: true, items, error: null }),
      (err: unknown): SectionState<Album> => ({
        ok: false,
        items: [],
        error: err instanceof ApiError ? err.message : 'Album search failed.',
      }),
    ),
  ])
  return { songs: songRes, albums: albumRes }
}

export function FindPage() {
  const [query, setQuery] = useState('')
  const [songs, setSongs] = useState<TrackSearchResult[]>([])
  const [albums, setAlbums] = useState<Album[]>([])
  const [allTags, setAllTags] = useState<Tag[]>([])
  const [songError, setSongError] = useState<string | null>(null)
  const [albumError, setAlbumError] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const latestQuery = useRef('')

  useEffect(() => {
    let cancelled = false
    api
      .getTags()
      .then((rows) => {
        if (!cancelled) setAllTags(rows)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const q = query.trim()
    latestQuery.current = q
    if (!q) {
      setSongs([])
      setAlbums([])
      setSongError(null)
      setAlbumError(null)
      setSearching(false)
      return
    }
    setSearching(true)
    const timer = setTimeout(async () => {
      const { songs: s, albums: a } = await runLibrarySearch(q)
      if (latestQuery.current !== q) return
      setSongs(s.items)
      setAlbums(a.items)
      setSongError(s.ok ? null : s.error)
      setAlbumError(a.ok ? null : a.error)
      setSearching(false)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  const q = query.trim().toLowerCase()
  const tagHits = q ? allTags.filter((t) => t.name.includes(q)) : []
  const anyResults = songs.length > 0 || albums.length > 0 || tagHits.length > 0

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Find</h1>
        <p className="muted">Search songs, albums, and mood tags across your shelf.</p>
      </div>

      <div className="search-box">
        <Search size={18} aria-hidden className="search-icon" />
        <input
          type="search"
          aria-label="Search your library"
          placeholder="Song, album, artist, tag…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {searching && <span className="muted search-hint">Searching…</span>}
      </div>

      {!query.trim() && (
        <div className="empty-state">
          <h2>Search your library</h2>
          <p className="muted">
            Type a song title, artist, album, or mood tag — like “chill” — to find
            records across your shelf.
          </p>
        </div>
      )}

      {query.trim() && !searching && !anyResults && !songError && !albumError && (
        <div className="empty-state">
          <h2>Nothing matched</h2>
          <p className="muted">No songs, albums, or tags found for “{query.trim()}”.</p>
        </div>
      )}

      {query.trim() && tagHits.length > 0 && (
        <section className="search-section" aria-label="Matching tags">
          <h2>Tags ({tagHits.length})</h2>
          <div className="tag-filter">
            {tagHits.map((tag) => (
              <Link
                key={tag.id}
                to={`/?tag=${encodeURIComponent(tag.name)}`}
                className="tag-chip tag-chip-link"
              >
                {tag.name}
                <span className="tag-count">{tag.album_count}</span>
              </Link>
            ))}
          </div>
          <p className="muted">
            Pick a tag to browse every album with it on the shelf.
          </p>
        </section>
      )}

      <section className="search-section" aria-label="Songs">
        <h2>Songs ({songs.length})</h2>
        {songError && (
          <p className="muted" role="alert">
            Songs unavailable: {songError}
          </p>
        )}
        {songs.length > 0 && (
          <ul className="result-list">
            {songs.map((song) => (
              <li key={song.id}>
                <Link to={`/album/${song.album.id}`} className="result-row song-row">
                  <CoverImage
                    albumId={song.album.id}
                    coverUrl={song.album.cover_url}
                    alt={`${song.album.title} cover`}
                    className="result-cover"
                  />
                  <span className="result-info">
                    <span className="result-title">{song.title}</span>
                    <span className="result-sub">
                      {song.album.artist}
                      {song.album.title ? ` · ${song.album.title}` : ''}
                      {song.album.year ? ` · ${song.album.year}` : ''}
                    </span>
                  </span>
                  <span className="track-duration">
                    {formatDuration(song.duration_seconds)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="search-section" aria-label="Albums">
        <h2>Albums ({albums.length})</h2>
        {albumError && (
          <p className="muted" role="alert">
            Albums unavailable: {albumError}
          </p>
        )}
        {albums.length > 0 && (
          <div className="shelf-grid">
            {albums.map((album) => (
              <AlbumCard key={album.id} album={album} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}