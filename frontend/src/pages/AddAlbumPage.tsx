import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Disc3, Plus, RefreshCw, Search } from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { SearchResult } from '../types'
import { CoverImage } from '../components/CoverImage'
import { SourceBadge } from '../components/SourceBadge'
import { AlbumPreviewModal } from '../components/AlbumPreviewModal'

const DEBOUNCE_MS = 300

type RowStatus =
  | { kind: 'idle' }
  | { kind: 'pending' }
  | { kind: 'added'; albumId: number; already: boolean }
  | { kind: 'error'; message: string }

export function parseConflictId(message: string): number | null {
  // Backend 409 detail: "Album already in your shelf (id=12)"
  const match = /\(id=(\d+)\)/.exec(message)
  return match ? Number(match[1]) : null
}

export function AddAlbumPage() {
  const { canEdit } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [rows, setRows] = useState<Record<string, RowStatus>>({})
  const [searchKey, setSearchKey] = useState(0)
  const [previewRow, setPreviewRow] = useState<SearchResult | null>(null)
  const latestQuery = useRef('')

  // Debounced external search; stale responses are dropped.
  useEffect(() => {
    const q = query.trim()
    latestQuery.current = q
    if (!q) {
      setResults([])
      setSearchError(null)
      setSearching(false)
      return
    }
    setSearching(true)
    const timer = setTimeout(async () => {
      try {
        const found = await api.searchAlbums(q)
        if (latestQuery.current !== q) return
        setResults(found)
        setSearchError(null)
      } catch (err) {
        if (latestQuery.current !== q) return
        setSearchError(
          err instanceof ApiError ? err.message : 'Search failed. Please try again.',
        )
        setResults([])
      } finally {
        if (latestQuery.current === q) setSearching(false)
      }
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query, searchKey])

  function setRow(key: string, status: RowStatus) {
    setRows((prev) => ({ ...prev, [key]: status }))
  }

  const rowKey = (r: SearchResult) => `${r.source}:${r.external_id}`

  async function importRow(result: SearchResult) {
    if (!canEdit) return
    const key = rowKey(result)
    setRow(key, { kind: 'pending' })
    try {
      const album = await api.importAlbum({
        source: result.source,
        external_id: result.external_id,
      })
      setRow(key, { kind: 'added', albumId: album.id, already: false })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const existingId = parseConflictId(err.message)
        setRow(key, {
          kind: 'added',
          albumId: existingId ?? 0,
          already: true,
        })
        return
      }
      setRow(key, {
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Import failed.',
      })
    }
  }

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Add an album</h1>
        <p className="muted">
          Search results come from <strong>MusicBrainz</strong>,{' '}
          <strong>Deezer</strong>, <strong>iTunes</strong>, and{' '}
          <strong>Discogs</strong> — metadata and artwork © their respective
          providers. Discogs needs a personal access token to appear in results.
        </p>
      </div>

      <div className="search-box">
        <Search size={18} aria-hidden className="search-icon" />
        <input
          type="search"
          aria-label="Search for an album"
          placeholder="Search by album title or artist…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        {searching && (
          <span className="muted search-hint" role="status">
            Searching…
          </span>
        )}
      </div>

      {searchError && (
        <div className="error-banner" role="alert">
          {searchError}{' '}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setSearchKey((k) => k + 1)}
          >
            <RefreshCw size={13} aria-hidden /> Retry
          </button>
        </div>
      )}

      {!query.trim() && (
        <div className="empty-state">
          <Disc3 size={36} aria-hidden />
          <h2>Find your next record</h2>
          <p className="muted">
            Type a title or artist above — we’ll search MusicBrainz, Deezer,
            iTunes, and Discogs for matches.
          </p>
        </div>
      )}

      {query.trim() && !searching && !searchError && results.length === 0 && (
        <div className="empty-state">
          <h2>No results</h2>
          <p className="muted">Nothing found for “{query.trim()}”.</p>
        </div>
      )}

      {results.length > 0 && (
        <ul className="result-list" aria-live="polite">
          {results.map((result) => {
            const key = rowKey(result)
            const status = rows[key] ?? { kind: 'idle' }
            return (
              <li key={key} className="result-row">
                <CoverImage
                  albumId={null}
                  coverUrl={result.cover_url}
                  alt={`${result.title} cover`}
                  className="result-cover"
                />
                <div className="result-info">
                  <button
                    type="button"
                    className="result-title result-title-btn"
                    aria-label={`Preview ${result.title} by ${result.artist}`}
                    onClick={() => setPreviewRow(result)}
                  >
                    {result.title}
                  </button>
                  <span className="result-sub">
                    {result.artist}
                    {result.year ? ` · ${result.year}` : ''}
                    {result.track_count
                      ? ` · ${result.track_count} tracks`
                      : ''}
                  </span>
                  {status.kind === 'error' && (
                    <>
                      <span className="result-error" role="alert">
                        {status.message}
                      </span>
                      <span className="result-hint">
                        The music service may be briefly unavailable — check your
                        connection and hit Retry, or try a different search.
                      </span>
                    </>
                  )}
                </div>
                <SourceBadge source={result.source} />

                {status.kind === 'added' ? (
                  status.albumId > 0 ? (
                    <Link
                      to={`/album/${status.albumId}`}
                      className="btn btn-sm btn-primary"
                    >
                      {status.already ? 'View album' : 'On your shelf — view'}
                    </Link>
                  ) : (
                    <span className="muted">Already added</span>
                  )
                ) : status.kind === 'error' ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={!canEdit}
                    onClick={() => importRow(result)}
                  >
                    <RefreshCw size={13} aria-hidden /> Retry
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    disabled={!canEdit || status.kind === 'pending'}
                    onClick={() => importRow(result)}
                  >
                    {status.kind === 'pending' ? (
                      <>
                        <span className="spinner" aria-hidden /> Adding…
                      </>
                    ) : (
                      <>
                        <Plus size={14} aria-hidden /> Import
                      </>
                    )}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {previewRow && (
        <AlbumPreviewModal row={previewRow} onClose={() => setPreviewRow(null)} />
      )}

      <div className="manual-entry-note">
        <Link to="/add/manual">Can’t find it? Enter the album manually</Link>
      </div>
    </div>
  )
}
