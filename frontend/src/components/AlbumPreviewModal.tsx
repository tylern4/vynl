import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, RefreshCw, X } from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { AlbumPreview, SearchResult } from '../types'
import { parseConflictId } from '../pages/AddAlbumPage'
import { CoverImage } from './CoverImage'
import { SourceBadge } from './SourceBadge'
import { formatDuration, formatRuntime, sumDurations } from '../format'

interface AlbumPreviewModalProps {
  /** The search row that was clicked; its already-loaded data shells the modal. */
  row: SearchResult
  onClose: () => void
}

type ImportStatus =
  | { kind: 'idle' }
  | { kind: 'pending' }
  | { kind: 'added'; albumId: number; already: boolean }
  | { kind: 'error'; message: string }

function sourceLabel(name: string): string {
  if (name === 'deezer') return 'Deezer'
  if (name === 'musicbrainz') return 'MusicBrainz'
  if (name === 'cover_art_archive') return 'Cover Art Archive'
  return name
}

/**
 * Dry-run preview (#13): shows exactly what importing this search result would
 * create — cover, metadata, tracklist, and which provider fed each part —
 * before the user commits. Preview fetch is read-only; the Import button in
 * the footer calls the normal (write) `api.importAlbum` fast path.
 */
export function AlbumPreviewModal({ row, onClose }: AlbumPreviewModalProps) {
  const { canEdit } = useAuth()
  const [preview, setPreview] = useState<AlbumPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadKey, setLoadKey] = useState(0)
  const [selectedSource, setSelectedSource] = useState<string | null>(null)
  const [importStatus, setImportStatus] = useState<ImportStatus>({ kind: 'idle' })
  const dialogRef = useRef<HTMLDivElement>(null)

  // Fetch the dry-run preview on open; Retry bumps loadKey.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    api
      .previewAlbum({ source: row.source, external_id: row.external_id })
      .then((data) => {
        if (cancelled) return
        setPreview(data)
        // Preferred tracklist source preselected when a toggle is offered.
        const preferred = data.source_breakdown.tracklist_source
        setSelectedSource(
          preferred && data.tracklists_by_source[preferred] ? preferred : null,
        )
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(
          err instanceof ApiError ? err.message : 'Could not load the preview.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [row.source, row.external_id, loadKey])

  // Move focus into the dialog on open; restore it on close.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    dialogRef.current?.focus()
    return () => previouslyFocused?.focus()
  }, [])

  // Esc closes; the backdrop click handler covers pointer dismissal.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Lock body scroll while the modal is open.
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  async function importAlbum() {
    if (!canEdit) return
    setImportStatus({ kind: 'pending' })
    try {
      const album = await api.importAlbum({
        source: row.source,
        external_id: row.external_id,
      })
      setImportStatus({ kind: 'added', albumId: album.id, already: false })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const existingId = parseConflictId(err.message)
        setImportStatus({ kind: 'added', albumId: existingId ?? 0, already: true })
        return
      }
      setImportStatus({
        kind: 'error',
        message: err instanceof ApiError ? err.message : 'Import failed.',
      })
    }
  }

  const title = preview?.title ?? row.title
  const coverUrl = preview?.cover_url ?? row.cover_url
  const tracklistSources = preview ? Object.keys(preview.tracklists_by_source) : []
  const activeSource =
    selectedSource ??
    (preview
      ? preview.source_breakdown.tracklist_source ?? tracklistSources[0] ?? null
      : null)
  const shownTracks =
    activeSource && preview?.tracklists_by_source[activeSource]
      ? preview.tracklists_by_source[activeSource]
      : (preview?.tracks ?? [])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="preview-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="preview-title">{title}</h2>
          <button
            type="button"
            className="icon-btn modal-close"
            aria-label="Close preview"
            onClick={onClose}
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="modal-body">
          {loading && (
            <div className="preview-status" role="status">
              <span className="spinner" aria-hidden /> Loading preview…
            </div>
          )}

          {!loading && loadError && (
            <div className="error-banner" role="alert">
              {loadError}{' '}
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setLoadKey((k) => k + 1)}
              >
                <RefreshCw size={13} aria-hidden /> Retry
              </button>
            </div>
          )}

          {!loading && !loadError && preview && (
            <>
              <div className="preview-grid">
                <CoverImage
                  albumId={null}
                  coverUrl={coverUrl}
                  alt={`${title} cover`}
                  className="preview-cover"
                />
                <div className="preview-info">
                  <p className="preview-artist">{preview.artist}</p>
                  <div className="meta-row">
                    <SourceBadge source={row.source} />
                    {preview.year ? <span>{preview.year}</span> : null}
                    {preview.label ? <span>{preview.label}</span> : null}
                    {preview.country ? <span>{preview.country}</span> : null}
                    <span>
                      {preview.track_count} track{preview.track_count === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>
              </div>

              <section className="card section" aria-labelledby="preview-tracklist">
                <h2 id="preview-tracklist">Tracklist</h2>
                {tracklistSources.length > 1 && (
                  <div
                    className="tracklist-toggle"
                    role="group"
                    aria-label="Tracklist source"
                  >
                    <span className="muted">Compare tracklists:</span>
                    {tracklistSources.map((name) => (
                      <button
                        key={name}
                        type="button"
                        className={`btn btn-sm${activeSource === name ? ' btn-primary' : ''}`}
                        aria-pressed={activeSource === name}
                        onClick={() => setSelectedSource(name)}
                      >
                        {sourceLabel(name)} ·{' '}
                        {preview.tracklists_by_source[name].length} tracks
                      </button>
                    ))}
                  </div>
                )}
                {activeSource && tracklistSources.length > 1 && (
                  <p className="muted tracklist-source-note">
                    Showing the {sourceLabel(activeSource)} pressing.
                  </p>
                )}
                {shownTracks.length === 0 ? (
                  <p className="muted">No tracklist on file for this record.</p>
                ) : (
                  <div className="tracklist-scroll">
                    <table className="tracklist">
                      <thead>
                        <tr>
                          <th scope="col">#</th>
                          <th scope="col">Title</th>
                          <th scope="col" className="track-duration">
                            Length
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {shownTracks.map((track) => (
                          <tr key={`${activeSource ?? 'preview'}:${track.position}`}>
                            <td className="track-position">{track.position}</td>
                            <td>{track.title}</td>
                            <td className="track-duration">
                              {formatDuration(track.duration_seconds)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <td colSpan={2}>
                            {shownTracks.length} track
                            {shownTracks.length === 1 ? '' : 's'}
                          </td>
                          <td className="track-duration">
                            {formatRuntime(
                              sumDurations(shownTracks.map((t) => t.duration_seconds)),
                            )}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </section>

              <section className="card section" aria-labelledby="preview-sources">
                <h2 id="preview-sources">Sources</h2>
                <div className="source-breakdown">
                  {preview.source_breakdown.metadata_source && (
                    <span
                      className={`breakdown-badge breakdown-${preview.source_breakdown.metadata_source}`}
                    >
                      Metadata from {sourceLabel(preview.source_breakdown.metadata_source)}
                    </span>
                  )}
                  {preview.source_breakdown.tracklist_source && (
                    <span
                      className={`breakdown-badge breakdown-${preview.source_breakdown.tracklist_source}`}
                    >
                      Tracklist from {sourceLabel(preview.source_breakdown.tracklist_source)}
                    </span>
                  )}
                  {preview.source_breakdown.artwork_source && (
                    <span
                      className={`breakdown-badge breakdown-${preview.source_breakdown.artwork_source}`}
                    >
                      Artwork from {sourceLabel(preview.source_breakdown.artwork_source)}
                    </span>
                  )}
                  {!preview.source_breakdown.metadata_source &&
                    !preview.source_breakdown.tracklist_source &&
                    !preview.source_breakdown.artwork_source && (
                      <span className="muted">No source details available.</span>
                    )}
                </div>
              </section>
            </>
          )}
        </div>

        <div className="modal-footer">
          {importStatus.kind === 'added' ? (
            importStatus.albumId > 0 ? (
              <Link
                to={`/album/${importStatus.albumId}`}
                className="btn btn-sm btn-primary"
              >
                {importStatus.already ? 'View album' : 'On your shelf — view'}
              </Link>
            ) : (
              <span className="muted">Already added</span>
            )
          ) : (
            <>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={!canEdit || importStatus.kind === 'pending' || loading}
                onClick={importAlbum}
              >
                {importStatus.kind === 'pending' ? (
                  <>
                    <span className="spinner" aria-hidden /> Adding…
                  </>
                ) : (
                  <>
                    <Plus size={14} aria-hidden /> Import this album
                  </>
                )}
              </button>
              <button type="button" className="btn btn-sm" onClick={onClose}>
                Cancel
              </button>
            </>
          )}
          {importStatus.kind === 'error' && (
            <span className="modal-footer-error" role="alert">
              {importStatus.message}{' '}
              <button type="button" className="btn btn-sm" onClick={importAlbum}>
                <RefreshCw size={13} aria-hidden /> Retry
              </button>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}