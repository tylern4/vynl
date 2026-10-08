import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Star } from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { Album, AlbumSort, Tag } from '../types'
import { AlbumCard } from '../components/AlbumCard'

const PAGE_SIZE = 500 // backend list cap (PLAN §5 / issue #3 note)
const MAX_PAGES = 20 // safety net: 10k albums

const SORT_OPTIONS: { value: AlbumSort; label: string }[] = [
  { value: 'added', label: 'Recently added' },
  { value: 'title', label: 'Title' },
  { value: 'artist', label: 'Artist' },
  { value: 'year', label: 'Year' },
  { value: 'played', label: 'Last played' },
]

/**
 * The shelf. Filtering approach (issue #5 decision): tag / favorite / sort run
 * **server-side** via `GET /api/albums` params (with paging), while the text
 * filter is **instant client-side** over the already-loaded list.
 */
export function ShelfPage() {
  const { canEdit } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTag = searchParams.get('tag') ?? ''

  const [albums, setAlbums] = useState<Album[]>([])
  const [tags, setTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [sort, setSort] = useState<AlbumSort>('added')
  const [favoritesOnly, setFavoritesOnly] = useState(false)

  const loadAlbums = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const all: Album[] = []
      let offset = 0
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const batch = await api.listAlbums({
          tag: activeTag || undefined,
          favorite: favoritesOnly || undefined,
          sort,
          limit: PAGE_SIZE,
          offset,
        })
        all.push(...batch)
        if (batch.length < PAGE_SIZE) break
        offset += PAGE_SIZE
      }
      setAlbums(all)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load your shelf.')
      setAlbums([])
    } finally {
      setLoading(false)
    }
  }, [activeTag, favoritesOnly, sort])

  useEffect(() => {
    loadAlbums()
  }, [loadAlbums])

  useEffect(() => {
    let cancelled = false
    api
      .getTags()
      .then((rows) => {
        if (!cancelled) setTags(rows)
      })
      .catch(() => {
        if (!cancelled) setTags([]) // tag filter chips are non-critical
      })
    return () => {
      cancelled = true
    }
  }, [])

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return albums
    return albums.filter(
      (a) =>
        a.title.toLowerCase().includes(needle) ||
        a.artist.toLowerCase().includes(needle),
    )
  }, [albums, filter])

  function setTagParam(tag: string | null) {
    const next = new URLSearchParams(searchParams)
    if (tag) next.set('tag', tag)
    else next.delete('tag')
    setSearchParams(next, { replace: true })
  }

  async function toggleFavorite(album: Album) {
    if (!canEdit) return
    try {
      const updated = await api.updateAlbum(album.id, { favorite: !album.favorite })
      setAlbums((prev) =>
        prev.map((a) => (a.id === updated.id ? { ...a, favorite: updated.favorite } : a)),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update favorite.')
    }
  }

  const emptyShelf = !loading && !error && albums.length === 0
  const noMatches = !loading && !error && albums.length > 0 && visible.length === 0

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>The shelf</h1>
        <p className="muted">
          {loading
            ? 'Loading records…'
            : `${visible.length} of ${albums.length} record${albums.length === 1 ? '' : 's'}`}
        </p>
      </div>

      <div className="shelf-toolbar">
        <input
          type="search"
          aria-label="Filter albums"
          placeholder="Filter by title or artist…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <select
          aria-label="Sort albums"
          value={sort}
          onChange={(e) => setSort(e.target.value as AlbumSort)}
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={`btn btn-sm${favoritesOnly ? ' btn-primary' : ''}`}
          aria-pressed={favoritesOnly}
          onClick={() => setFavoritesOnly((v) => !v)}
        >
          <Star size={14} fill={favoritesOnly ? 'currentColor' : 'none'} aria-hidden />
          Favorites
        </button>
      </div>

      <div className="tag-filter" role="group" aria-label="Filter by tag">
        <button
          type="button"
          className={`tag-chip tag-chip-btn${activeTag === '' ? ' is-active' : ''}`}
          aria-pressed={activeTag === ''}
          onClick={() => setTagParam(null)}
        >
          All
        </button>
        {tags.map((tag) => (
          <button
            key={tag.id}
            type="button"
            className={`tag-chip tag-chip-btn${activeTag === tag.name ? ' is-active' : ''}`}
            aria-pressed={activeTag === tag.name}
            onClick={() => setTagParam(activeTag === tag.name ? null : tag.name)}
          >
            {tag.name}
            <span className="tag-count">{tag.album_count}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}{' '}
          <button type="button" className="btn btn-sm" onClick={loadAlbums}>
            Retry
          </button>
        </div>
      )}

      {loading && (
        <div className="shelf-skeleton-grid" data-testid="shelf-skeleton" aria-hidden="true">
          {[0, 1, 2, 3, 4, 5].map((k) => (
            <div key={k} className="shelf-skeleton">
              <div className="shelf-skeleton-cover" />
              <div className="shelf-skeleton-lines">
                <div className="shelf-skeleton-line" />
                <div className="shelf-skeleton-line short" />
              </div>
            </div>
          ))}
        </div>
      )}

      {emptyShelf && (
        <div className="empty-state">
          <h2>Shelf is empty — add your first record</h2>
          <p className="muted">Search MusicBrainz and Deezer to start your collection.</p>
          <Link to="/add" className="btn btn-primary">
            <Plus size={16} aria-hidden /> Add your first record
          </Link>
        </div>
      )}

      {noMatches && (
        <div className="empty-state">
          <h2>No albums match</h2>
          <p className="muted">
            Nothing on the shelf matches “{filter.trim() || activeTag}”.
          </p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setFilter('')
              if (activeTag) setTagParam(null)
            }}
          >
            Clear filters
          </button>
        </div>
      )}

      {!loading && visible.length > 0 && (
        <div className="shelf-grid" data-testid="shelf-grid" aria-live="polite">
          {visible.map((album) => (
            <AlbumCard
              key={album.id}
              album={album}
              canEdit={canEdit}
              onToggleFavorite={toggleFavorite}
            />
          ))}
        </div>
      )}
    </div>
  )
}
