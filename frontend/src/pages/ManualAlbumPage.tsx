import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Plus, Trash2 } from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { ManualAlbumInput, ManualTrackInput } from '../types'
import { CoverPicker } from '../components/CoverPicker'
import { parseConflictId } from './AddAlbumPage'

export interface TrackDraft {
  title: string
  duration: string
}

interface FieldErrors {
  title?: string
  artist?: string
  year?: string
  tracks?: Record<number, string>
}

const MAX_YEAR = new Date().getFullYear() + 1

/**
 * Parse a track-duration input: `m:ss` or plain seconds. Returns `null` when
 * blank (not supplied — valid), or `'invalid'` for a supplied-but-unparseable
 * value.
 */
export function parseDurationInput(raw: string): number | null | 'invalid' {
  const s = raw.trim()
  if (!s) return null
  if (/^\d+$/.test(s)) return Number(s)
  const match = /^(\d+):([0-5]\d)$/.exec(s)
  if (match) return Number(match[1]) * 60 + Number(match[2])
  return 'invalid'
}

/** Entity type guard for the `'invalid'` sentinel. */
function isInvalidDuration(value: number | null | 'invalid'): value is 'invalid' {
  return value === 'invalid'
}

export function ManualAlbumPage() {
  const navigate = useNavigate()
  const { canEdit } = useAuth()

  const [title, setTitle] = useState('')
  const [artist, setArtist] = useState('')
  const [year, setYear] = useState('')
  const [label, setLabel] = useState('')
  const [country, setCountry] = useState('')
  const [note, setNote] = useState('')
  const [tracks, setTracks] = useState<TrackDraft[]>([])

  const [errors, setErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [conflictId, setConflictId] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [createdAlbumId, setCreatedAlbumId] = useState<number | null>(null)

  const [coverBlob, setCoverBlob] = useState<Blob | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  function updateTrack(index: number, patch: Partial<TrackDraft>) {
    setTracks((prev) =>
      prev.map((track, i) => (i === index ? { ...track, ...patch } : track)),
    )
  }

  function addTrack() {
    setTracks((prev) => [...prev, { title: '', duration: '' }])
  }

  function removeTrack(index: number) {
    setTracks((prev) => prev.filter((_, i) => i !== index))
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {}
    if (!title.trim()) next.title = 'Title is required'
    if (!artist.trim()) next.artist = 'Artist is required'
    if (year.trim()) {
      const parsed = Number(year)
      if (
        !Number.isInteger(parsed) ||
        parsed < 1000 ||
        parsed > MAX_YEAR
      ) {
        next.year = `Year must be between 1000 and ${MAX_YEAR}`
      }
    }
    const trackErrs: Record<number, string> = {}
    tracks.forEach((track, i) => {
      if (!track.title.trim() && !track.duration.trim()) return // empty = ignored
      if (!track.title.trim()) trackErrs[i] = 'Title is required'
      if (track.duration.trim() && isInvalidDuration(parseDurationInput(track.duration))) {
        trackErrs[i] = 'Duration must be like 3:45 or 225'
      }
    })
    if (Object.keys(trackErrs).length > 0) next.tracks = trackErrs
    return next
  }

  async function uploadCover(albumId: number) {
    if (!coverBlob) return
    setUploading(true)
    setUploadError(null)
    try {
      await api.uploadAlbumCover(albumId, coverBlob)
      navigate(`/album/${albumId}`)
    } catch (err) {
      setUploadError(
        err instanceof ApiError ? err.message : 'Could not upload the cover.',
      )
    } finally {
      setUploading(false)
    }
  }

  async function submit() {
    const nextErrors = validate()
    setErrors(nextErrors)
    setFormError(null)
    setConflictId(null)
    setUploadError(null)
    if (Object.keys(nextErrors).length > 0) return

    const input: ManualAlbumInput = {
      title: title.trim(),
      artist: artist.trim(),
      year: year.trim() ? Number(year) : undefined,
      label: label.trim() || undefined,
      country: country.trim() || undefined,
      note: note.trim() || undefined,
      tracks: tracks
        .filter((track) => track.title.trim())
        .map((track) => {
          const out: ManualTrackInput = { title: track.title.trim() }
          const seconds = parseDurationInput(track.duration)
          if (seconds !== null && !isInvalidDuration(seconds)) {
            out.duration_seconds = seconds
          }
          return out
        }),
    }

    setCreating(true)
    try {
      const album = await api.createManualAlbum(input)
      setCreatedAlbumId(album.id)
      if (coverBlob) {
        await uploadCover(album.id)
      } else {
        navigate(`/album/${album.id}`)
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setConflictId(parseConflictId(err.message))
      } else {
        setFormError(
          err instanceof ApiError ? err.message : 'Could not add the album.',
        )
      }
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Add an album manually</h1>
        <p className="muted">
          Obscure pressing and can’t find it in MusicBrainz or Deezer? Enter the
          details yourself — cover art can be added from a file or your phone
          camera.
        </p>
      </div>

      <form
        className="card manual-form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <div className="manual-fields">
          <div className="field">
            <label htmlFor="manual-title">Title *</label>
            <input
              id="manual-title"
              value={title}
              maxLength={500}
              autoFocus
              aria-invalid={Boolean(errors.title)}
              onChange={(e) => setTitle(e.target.value)}
            />
            {errors.title && (
              <span className="field-error" role="alert">{errors.title}</span>
            )}
          </div>
          <div className="field">
            <label htmlFor="manual-artist">Artist *</label>
            <input
              id="manual-artist"
              value={artist}
              maxLength={500}
              aria-invalid={Boolean(errors.artist)}
              onChange={(e) => setArtist(e.target.value)}
            />
            {errors.artist && (
              <span className="field-error" role="alert">{errors.artist}</span>
            )}
          </div>
          <div className="field manual-year">
            <label htmlFor="manual-year">Year</label>
            <input
              id="manual-year"
              type="number"
              min={1000}
              max={MAX_YEAR}
              placeholder="1983"
              value={year}
              aria-invalid={Boolean(errors.year)}
              onChange={(e) => setYear(e.target.value)}
            />
            {errors.year && (
              <span className="field-error" role="alert">{errors.year}</span>
            )}
          </div>
          <div className="field">
            <label htmlFor="manual-label">Label</label>
            <input
              id="manual-label"
              value={label}
              maxLength={255}
              placeholder="Horizon Records"
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="manual-country">Country</label>
            <input
              id="manual-country"
              value={country}
              maxLength={8}
              placeholder="JP, US, UK…"
              onChange={(e) => setCountry(e.target.value)}
            />
          </div>
          <div className="field field-full">
            <label htmlFor="manual-note">Note</label>
            <textarea
              id="manual-note"
              rows={3}
              value={note}
              placeholder="Pressing details, memories, where you found it…"
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>

        <section className="manual-section" aria-labelledby="manual-tracks-heading">
          <h2 id="manual-tracks-heading">Tracklist</h2>
          <p className="field-note">
            Optional. Durations accept <code>m:ss</code> (3:45) or seconds (225).
          </p>
          {tracks.length === 0 ? (
            <p className="muted">No tracks yet.</p>
          ) : (
            <div className="track-editor" aria-live="polite">
              {tracks.map((track, index) => (
                <div className="track-row" key={index}>
                  <span className="track-row-pos">{index + 1}</span>
                  <input
                    aria-label={`Track ${index + 1} title`}
                    value={track.title}
                    maxLength={500}
                    placeholder="Track title"
                    aria-invalid={Boolean(errors.tracks?.[index])}
                    onChange={(e) => updateTrack(index, { title: e.target.value })}
                  />
                  <input
                    aria-label={`Track ${index + 1} duration`}
                    value={track.duration}
                    placeholder="3:45"
                    aria-invalid={Boolean(errors.tracks?.[index])}
                    onChange={(e) => updateTrack(index, { duration: e.target.value })}
                  />
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    aria-label={`Remove track ${index + 1}`}
                    onClick={() => removeTrack(index)}
                  >
                    <Trash2 size={14} aria-hidden />
                  </button>
                  {errors.tracks?.[index] && (
                    <span className="field-error track-row-error" role="alert">
                      {errors.tracks[index]}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          <button
            type="button"
            className="btn btn-sm"
            disabled={!canEdit || creating}
            onClick={addTrack}
          >
            <Plus size={14} aria-hidden /> Add track
          </button>
        </section>

        <section className="manual-section" aria-labelledby="manual-cover-heading">
          <h2 id="manual-cover-heading">Cover art</h2>
          <p className="field-note">
            Optional — a phone photo or file is normalized to a JPEG before
            upload.
          </p>
          <CoverPicker onChange={setCoverBlob} disabled={!canEdit || creating} />
        </section>

        {formError && (
          <div className="error-banner" role="alert">{formError}</div>
        )}
        {conflictId !== null && (
          <div className="error-banner" role="alert">
            That album is already in your shelf.{' '}
            <Link to={`/album/${conflictId}`}>View album</Link>
          </div>
        )}
        {uploadError && createdAlbumId !== null && (
          <>
            <div className="error-banner" role="alert">
              The album was added, but the cover upload failed:{' '}
              {uploadError}. The album is on your shelf — Retry, or add a cover
              from the album page later.
            </div>
            <div className="detail-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={uploading}
                onClick={() => uploadCover(createdAlbumId)}
              >
                {uploading ? 'Uploading…' : 'Retry upload'}
              </button>
              <Link to={`/album/${createdAlbumId}`} className="btn btn-sm">
                View album
              </Link>
            </div>
          </>
        )}

        <div className="form-actions">
          <Link to="/add" className="btn">Back to search</Link>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!canEdit || creating || uploading}
          >
            {creating ? 'Adding…' : 'Add to shelf'}
          </button>
        </div>
      </form>
    </div>
  )
}