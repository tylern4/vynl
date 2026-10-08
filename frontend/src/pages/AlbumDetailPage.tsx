import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Disc3, ImagePlus, Star, Trash2 } from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { Album, Play, Tag } from '../types'
import { CoverImage } from '../components/CoverImage'
import { CoverPicker } from '../components/CoverPicker'
import { SourceBadge } from '../components/SourceBadge'
import { TagEditor } from '../components/TagEditor'
import {
  formatDate,
  formatDuration,
  formatRuntime,
  sumDurations,
  timeAgo,
} from '../format'

export function AlbumDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { canEdit } = useAuth()
  const albumId = Number(id)

  const [album, setAlbum] = useState<Album | null>(null)
  const [plays, setPlays] = useState<Play[]>([])
  const [allTags, setAllTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [noteDraft, setNoteDraft] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const [noteSaved, setNoteSaved] = useState(false)
  const [spinning, setSpinning] = useState(false)
  const [confirmingRemove, setConfirmingRemove] = useState(false)

  const [showCoverPicker, setShowCoverPicker] = useState(false)
  const [coverDraft, setCoverDraft] = useState<Blob | null>(null)
  const [savingCover, setSavingCover] = useState(false)
  const [coverSaved, setCoverSaved] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setLoadError(null)
      setNotFound(false)
      try {
        const a = await api.getAlbum(albumId)
        if (cancelled) return
        setAlbum(a)
        setNoteDraft(a.note ?? '')
      } catch (err) {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true)
          setLoadError('Album not found')
        } else {
          setLoadError(err instanceof ApiError ? err.message : 'Could not load this album.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    api
      .listPlays(albumId)
      .then((rows) => {
        if (!cancelled) setPlays(rows)
      })
      .catch(() => undefined) // history is non-critical
    api
      .getTags()
      .then((rows) => {
        if (!cancelled) setAllTags(rows)
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [albumId, reloadKey])

  function fail(err: unknown, fallback: string) {
    setActionError(err instanceof ApiError ? err.message : fallback)
  }

  async function toggleFavorite() {
    if (!album || !canEdit) return
    setActionError(null)
    try {
      setAlbum(await api.updateAlbum(album.id, { favorite: !album.favorite }))
    } catch (err) {
      fail(err, 'Could not update favorite.')
    }
  }

  async function saveNote() {
    if (!album || !canEdit) return
    setSavingNote(true)
    setActionError(null)
    try {
      const updated = await api.updateAlbum(album.id, { note: noteDraft })
      setAlbum(updated)
      setNoteDraft(updated.note ?? '')
      setNoteSaved(true)
    } catch (err) {
      fail(err, 'Could not save note.')
    } finally {
      setSavingNote(false)
    }
  }

  async function saveTags(next: string[]) {
    if (!album || !canEdit) return
    setActionError(null)
    try {
      const updated = await api.setAlbumTags(album.id, next)
      setAlbum(updated)
      // Refresh suggestion counts (new tags may have just been created).
      api.getTags().then(setAllTags).catch(() => undefined)
    } catch (err) {
      fail(err, 'Could not save tags.')
    }
  }

  async function spin() {
    if (!album || !canEdit) return
    setSpinning(true)
    setActionError(null)
    try {
      setAlbum(await api.logPlay(album.id))
      setPlays(await api.listPlays(album.id))
    } catch (err) {
      fail(err, 'Could not log play.')
    } finally {
      setSpinning(false)
    }
  }

  async function removePlay(playId: number) {
    if (!album || !canEdit) return
    setActionError(null)
    try {
      await api.deletePlay(album.id, playId)
      setPlays(await api.listPlays(album.id))
      // Server recomputes last_played_at on delete — resync the album row.
      setAlbum(await api.getAlbum(album.id))
    } catch (err) {
      fail(err, 'Could not delete play.')
    }
  }

  async function removeAlbum() {
    if (!album) return
    setActionError(null)
    try {
      await api.deleteAlbum(album.id)
      navigate('/', { replace: true })
    } catch (err) {
      fail(err, 'Could not remove album.')
      setConfirmingRemove(false)
    }
  }

  async function saveCover() {
    if (!album || !canEdit || !coverDraft) return
    setSavingCover(true)
    setActionError(null)
    setCoverSaved(false)
    try {
      const updated = await api.uploadAlbumCover(album.id, coverDraft)
      setAlbum(updated)
      setCoverDraft(null)
      setShowCoverPicker(false)
      setCoverSaved(true)
    } catch (err) {
      fail(err, 'Could not upload the cover image.')
    } finally {
      setSavingCover(false)
    }
  }

  if (loading) {
    return (
      <div className="page-inner">
        <div className="detail-skeleton" data-testid="detail-skeleton" aria-hidden="true">
          <div className="detail-skeleton-cover" />
          <div className="detail-skeleton-lines">
            <div className="detail-skeleton-line big" />
            <div className="detail-skeleton-line" />
            <div className="detail-skeleton-line short" />
            <div className="detail-skeleton-line" />
            <div className="detail-skeleton-line short" />
          </div>
        </div>
      </div>
    )
  }

  if (loadError || !album) {
    return (
      <div className="page-inner">
        <h1>{notFound ? 'Album not found' : 'Something went wrong'}</h1>
        {!notFound && loadError && <div className="error-banner">{loadError}</div>}
        <div className="detail-actions">
          <Link to="/" className="btn">
            Back to shelf
          </Link>
          {!notFound && (
            <button
              type="button"
              className="btn"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Retry
            </button>
          )}
        </div>
      </div>
    )
  }

  const tracks = album.tracks ?? []
  const totalRuntime = sumDurations(tracks.map((t) => t.duration_seconds))
  const lastSpent = timeAgo(album.last_played_at)

  return (
    <div className="page-inner">
      <div className="detail-grid">
        <div className="detail-cover">
          <CoverImage
            albumId={album.id}
            coverUrl={album.cover_url}
            alt={`${album.title} cover`}
            className="detail-cover-img"
          />
          {showCoverPicker && (
            <div className="cover-replace-block">
              <p className="field-note">
                A file or phone photo is normalized to a JPEG before upload.
              </p>
              <CoverPicker onChange={setCoverDraft} disabled={!canEdit || savingCover} />
              <div className="detail-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!canEdit || savingCover || !coverDraft}
                  onClick={saveCover}
                >
                  {savingCover ? 'Uploading…' : 'Save cover'}
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={savingCover}
                  onClick={() => {
                    setShowCoverPicker(false)
                    setCoverDraft(null)
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="detail-info">
          <h1>{album.title}</h1>
          <p className="detail-artist">{album.artist}</p>

          <div className="meta-row">
            <SourceBadge source={album.source} />
            {album.year && <span>{album.year}</span>}
            {album.label && <span>{album.label}</span>}
            {album.country && <span>{album.country}</span>}
          </div>

          <p className="last-played">
            {album.last_played_at
              ? `Last spun: ${lastSpent ?? formatDate(album.last_played_at)}`
              : 'Never spun'}
          </p>

          {actionError && (
            <div className="error-banner" role="alert">
              {actionError}
            </div>
          )}

          <div className="detail-actions">
            <button
              type="button"
              className={`btn${album.favorite ? ' btn-primary' : ''}`}
              aria-pressed={album.favorite}
              disabled={!canEdit}
              onClick={toggleFavorite}
            >
              <Star size={16} fill={album.favorite ? 'currentColor' : 'none'} aria-hidden />
              {album.favorite ? 'Favorited' : 'Favorite'}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!canEdit || spinning}
              onClick={spin}
            >
              <Disc3 size={16} aria-hidden /> {spinning ? 'Logging…' : 'I spun this'}
            </button>
            <button
              type="button"
              className="btn"
              disabled={!canEdit}
              onClick={() => setShowCoverPicker((v) => !v)}
            >
              <ImagePlus size={16} aria-hidden /> Replace cover
            </button>
            {coverSaved && !showCoverPicker && (
              <span className="muted">Cover updated.</span>
            )}
            <button
              type="button"
              className="btn btn-danger"
              disabled={!canEdit}
              onClick={() => setConfirmingRemove(true)}
            >
              <Trash2 size={16} aria-hidden /> Remove from shelf
            </button>
          </div>

          {confirmingRemove && (
            <div className="confirm-row">
              <span>
                Remove “{album.title}” from your shelf? This can’t be undone.
              </span>
              <div className="confirm-actions">
                <button type="button" className="btn btn-danger btn-sm" onClick={removeAlbum}>
                  Yes, remove it
                </button>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setConfirmingRemove(false)}
                >
                  Keep it
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <section className="card section">
        <h2>Tracklist</h2>
        {tracks.length === 0 ? (
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
              {tracks.map((track) => (
                <tr key={track.id}>
                  <td className="track-position">{track.position}</td>
                  <td>{track.title}</td>
                  <td className="track-duration">{formatDuration(track.duration_seconds)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={2}>
                  {tracks.length} track{tracks.length === 1 ? '' : 's'}
                </td>
                <td className="track-duration">{formatRuntime(totalRuntime)}</td>
              </tr>
            </tfoot>
          </table>
          </div>
        )}
      </section>

      <section className="card section">
        <h2>Tags</h2>
        <TagEditor
          tags={album.tags}
          suggestions={allTags}
          disabled={!canEdit}
          onAdd={(name) => saveTags([...album.tags, name])}
          onRemove={(name) => saveTags(album.tags.filter((t) => t !== name))}
        />
      </section>

      <section className="card section">
        <h2>Notes</h2>
        <div className="field">
          <label htmlFor="album-note">Personal note</label>
          <textarea
            id="album-note"
            rows={4}
            value={noteDraft}
            disabled={!canEdit}
            placeholder="Pressing details, memories, where you found it…"
            onChange={(e) => {
              setNoteDraft(e.target.value)
              setNoteSaved(false)
            }}
          />
        </div>
        <div className="detail-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!canEdit || savingNote || noteDraft === (album.note ?? '')}
            onClick={saveNote}
          >
            {savingNote ? 'Saving…' : 'Save note'}
          </button>
          {noteSaved && <span className="muted">Saved.</span>}
        </div>
      </section>

      <section className="card section" aria-labelledby="play-history-heading">
        <h2 id="play-history-heading">Play history</h2>
        <div aria-live="polite">
          {plays.length === 0 ? (
            <p className="muted">No spins logged yet — hit “I spun this”.</p>
          ) : (
            <ol className="play-list">
              {plays.map((play) => (
                <li key={play.id}>
                  <span>
                    {timeAgo(play.played_at) ?? '—'}{' '}
                    <span className="muted">({formatDate(play.played_at)})</span>
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    aria-label="Delete play"
                    disabled={!canEdit}
                    onClick={() => removePlay(play.id)}
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>
    </div>
  )
}
