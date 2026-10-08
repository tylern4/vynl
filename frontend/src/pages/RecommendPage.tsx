import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check,
  Clock3,
  Dices,
  Loader2,
  Plus,
  RefreshCw,
  Shuffle,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import type { Recommendation, RecommendationMode, Tag } from '../types'
import { CoverImage } from '../components/CoverImage'

/** PLAN §5 recommends n=3 for the slate ("feels right" per issue #6). */
const SPIN_COUNT = 3
/** Safety net when a tiny shelf keeps returning the same record on re-roll. */
const MAX_REROLL_ATTEMPTS = 5

type SpinStatus = 'idle' | 'loading' | 'ready' | 'error'

interface RecCard {
  rec: Recommendation
  justSpun: boolean
  busy: 'reroll' | 'log' | null
  /** True when a reroll had to accept a record already on screen (tiny shelf). */
  repeat?: boolean
}

const MODE_META: Record<RecommendationMode, { hint: string }> = {
  dusty: { hint: 'Records you haven’t spun in a while.' },
  random: { hint: 'A pure-chance pick from your whole shelf.' },
}

/**
 * Dusty/random picker: mode + optional tag chips, a "Spin" that pulls a
 * 3-card slate from `GET /api/recommendations`, per-card "Spun it" (logs a
 * play) and "Show me another" (re-rolls just that slot), linking through to
 * the album detail page.
 */
export function RecommendPage() {
  const { canEdit } = useAuth()
  const [mode, setMode] = useState<RecommendationMode>('dusty')
  const [selectedTag, setSelectedTag] = useState('')
  const [allTags, setAllTags] = useState<Tag[]>([])
  const [cards, setCards] = useState<RecCard[]>([])
  const [status, setStatus] = useState<SpinStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  // Invalidate in-flight requests whenever the selection or a spin changes.
  const seq = useRef(0)
  // StrictMode re-runs mount effects on the same instance; spin once.
  const autoStarted = useRef(false)

  useEffect(() => {
    let cancelled = false
    api
      .getTags()
      .then((rows) => {
        if (!cancelled) setAllTags(rows)
      })
      .catch(() => undefined) // mood chips are non-critical
    return () => {
      cancelled = true
    }
  }, [])

  // Auto-spin on mount so the page isn't an empty form.
  useEffect(() => {
    if (autoStarted.current) return
    autoStarted.current = true
    spinFor('dusty', '')
    // No `cancelled` cleanup: the ref guard already prevents the StrictMode
    // double-run, and a cleanup would silently drop the single request.
  }, [])

  function spinFor(modeArg: RecommendationMode, tagArg: string) {
    const id = ++seq.current
    setStatus('loading')
    setError(null)
    api
      .getRecommendations({ mode: modeArg, tag: tagArg || undefined, n: SPIN_COUNT })
      .then((recs) => {
        if (id !== seq.current) return
        setCards(recs.map((rec) => ({ rec, justSpun: false, busy: null })))
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (id !== seq.current) return
        setStatus('error')
        setError(err instanceof ApiError ? err.message : 'Could not get recommendations.')
      })
  }

  function changeMode(next: RecommendationMode) {
    seq.current += 1
    setMode(next)
    setCards([])
    setError(null)
    setStatus('idle')
  }

  function pickTag(name: string) {
    seq.current += 1
    setSelectedTag(name)
    setCards([])
    setError(null)
    setStatus('idle')
  }

  function setCardBusy(index: number, busy: RecCard['busy']) {
    setCards((prev) => prev.map((c, i) => (i === index ? { ...c, busy } : c)))
  }

  function replaceCard(index: number, rec: Recommendation, patch: Partial<RecCard> = {}) {
    setCards((prev) => prev.map((c, i) => (i === index ? { ...c, rec, ...patch } : c)))
  }

  async function spunIt(index: number) {
    const card = cards[index]
    if (!card || card.busy || !canEdit) return
    setCardBusy(index, 'log')
    setError(null)
    const id = seq.current
    try {
      const album = await api.logPlay(card.rec.album.id)
      if (id !== seq.current) return
      replaceCard(
        index,
        { album, reason: 'Logged — happy spinning!', days_since_played: 0 },
        { justSpun: true, repeat: false },
      )
    } catch (err) {
      if (id !== seq.current) return
      setError(err instanceof ApiError ? err.message : 'Could not log the play.')
    } finally {
      if (id === seq.current) setCardBusy(index, null)
    }
  }

  async function reroll(index: number) {
    const card = cards[index]
    if (!card || card.busy) return
    setCardBusy(index, 'reroll')
    setError(null)
    const id = seq.current
    try {
      // Re-roll just this slot; avoid landing on a card already on screen
      // when the shelf has alternatives.
      const others = new Set(cards.map((c, i) => (i === index ? -1 : c.rec.album.id)))
      let picked: Recommendation | null = null
      for (let attempt = 0; attempt < MAX_REROLL_ATTEMPTS; attempt += 1) {
        const [rec] = await api.getRecommendations({
          mode,
          tag: selectedTag || undefined,
          n: 1,
        })
        if (id !== seq.current) return
        if (!rec) break
        picked = rec
        if (!others.has(rec.album.id)) break
      }
      // The accepted pick visibly duplicates a card already on screen (this slot
      // included) → tell the user why the reroll repeated on a tiny shelf.
      const onScreen = new Set(cards.map((c) => c.rec.album.id))
      if (picked) {
        replaceCard(index, picked, {
          justSpun: false,
          repeat: onScreen.has(picked.album.id),
        })
      }
    } catch (err) {
      if (id !== seq.current) return
      setError(err instanceof ApiError ? err.message : 'Could not re-roll this card.')
    } finally {
      if (id === seq.current) setCardBusy(index, null)
    }
  }

  const anyBusy = cards.some((c) => c.busy !== null)
  const spinning = status === 'loading'
  const ReasonIcon = mode === 'random' ? Shuffle : Clock3

  return (
    <div className="page-inner">
      <div className="page-head">
        <h1>Recommend</h1>
        <p className="muted">The shelf’s answer to “what should I spin?”</p>
      </div>

      <div className="rec-controls">
        <div className="rec-row">
          <div className="mode-toggle" role="group" aria-label="Recommendation mode">
            <button
              type="button"
              className={mode === 'dusty' ? 'is-active' : ''}
              aria-pressed={mode === 'dusty'}
              onClick={() => changeMode('dusty')}
            >
              <Clock3 size={15} aria-hidden /> Dusty
            </button>
            <button
              type="button"
              className={mode === 'random' ? 'is-active' : ''}
              aria-pressed={mode === 'random'}
              onClick={() => changeMode('random')}
            >
              <Shuffle size={15} aria-hidden /> Random
            </button>
          </div>
          <div className="rec-spin-row">
            <button
              type="button"
              className="btn btn-primary"
              disabled={spinning || anyBusy}
              onClick={() => spinFor(mode, selectedTag)}
            >
              {spinning ? (
                <span className="spinner" aria-hidden />
              ) : (
                <Dices size={16} aria-hidden />
              )}
              {spinning ? 'Spinning…' : 'Spin'}
            </button>
            <p className="muted mode-hint">{MODE_META[mode].hint}</p>
          </div>
        </div>

        {allTags.length > 0 && (
          <div className="tag-filter" role="group" aria-label="Filter by tag">
            <button
              type="button"
              className={`tag-chip tag-chip-btn${selectedTag === '' ? ' is-active' : ''}`}
              aria-pressed={selectedTag === ''}
              onClick={() => pickTag('')}
            >
              Any mood
            </button>
            {allTags.map((tag) => (
              <button
                key={tag.id}
                type="button"
                className={`tag-chip tag-chip-btn${selectedTag === tag.name ? ' is-active' : ''}`}
                aria-pressed={selectedTag === tag.name}
                onClick={() => pickTag(selectedTag === tag.name ? '' : tag.name)}
              >
                {tag.name}
                <span className="tag-count">{tag.album_count}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}{' '}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => spinFor(mode, selectedTag)}
          >
            Retry
          </button>
        </div>
      )}

      {cards.length > 0 ? (
        <div className="rec-grid" data-testid="rec-grid" aria-live="polite">
          {cards.map((card, i) => (
            <article className="rec-card" key={i}>
              <Link to={`/album/${card.rec.album.id}`} className="rec-cover-link">
                <CoverImage
                  albumId={card.rec.album.id}
                  coverUrl={card.rec.album.cover_url}
                  alt={`${card.rec.album.title} cover`}
                  className="rec-cover"
                />
              </Link>
              <div className="rec-body">
                <Link to={`/album/${card.rec.album.id}`} className="rec-title-link">
                  <h3 className="rec-title">{card.rec.album.title}</h3>
                </Link>
                <p className="rec-artist">{card.rec.album.artist}</p>
                <p className="rec-reason">
                  <ReasonIcon size={14} aria-hidden /> {card.rec.reason}
                </p>
                {!card.justSpun && card.rec.days_since_played !== null && (
                  <span className="rec-days">
                    {card.rec.days_since_played} day
                    {card.rec.days_since_played === 1 ? '' : 's'} since spun
                  </span>
                )}
                <div className="rec-actions">
                  {card.justSpun ? (
                    <span className="rec-spun">
                      <Check size={14} aria-hidden /> Logged
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={!canEdit || card.busy !== null}
                      title={!canEdit ? 'Read-only account cannot log plays' : undefined}
                      onClick={() => spunIt(i)}
                    >
                      {card.busy === 'log' ? (
                        <Loader2 size={14} className="loader-spin" aria-hidden />
                      ) : (
                        <Check size={14} aria-hidden />
                      )}
                      {card.busy === 'log' ? 'Logging…' : 'Spun it'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={card.busy !== null}
                    onClick={() => reroll(i)}
                  >
                    {card.busy === 'reroll' ? (
                      <Loader2 size={14} className="loader-spin" aria-hidden />
                    ) : (
                      <RefreshCw size={14} aria-hidden />
                    )}
                    {card.busy === 'reroll' ? 'Rolling…' : 'Show me another'}
                  </button>
                </div>
                {card.repeat && (
                  <p className="rec-repeat">
                    Tiny shelf — only a handful of records match, so rerolls fall back to
                    repeats.
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : spinning ? (
        <div className="rec-grid" aria-hidden="true">
          {[0, 1, 2].map((k) => (
            <div key={k} className="rec-skeleton" data-testid="rec-skeleton">
              <div className="rec-skeleton-cover" />
              <div className="rec-skeleton-lines">
                <div className="rec-skeleton-line" />
                <div className="rec-skeleton-line short" />
                <div className="rec-skeleton-line short" />
              </div>
            </div>
          ))}
        </div>
      ) : status === 'ready' ? (
        selectedTag ? (
          <div className="empty-state">
            <h2>No records tagged “{selectedTag}”</h2>
            <p className="muted">Try another mood, or clear the tag and spin again.</p>
            <button type="button" className="btn" onClick={() => pickTag('')}>
              Clear tag
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <h2>Shelf is empty — add records to get picks</h2>
            <p className="muted">
              Recommendations come from your own shelf. Import a few records first.
            </p>
            <Link to="/add" className="btn btn-primary">
              <Plus size={16} aria-hidden /> Add a record
            </Link>
          </div>
        )
      ) : status === 'idle' ? (
        <div className="rec-prompt">
          <p className="muted">
            <Dices size={18} aria-hidden /> Pick a mode and any mood tag, then hit Spin.
          </p>
        </div>
      ) : null}
    </div>
  )
}