/** Duration/time formatting helpers shared by the shelf, detail, and find pages. */

/** Seconds → `m:ss` (minutes unbounded, e.g. `12:05`); null-safe `—`. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—'
  const total = Math.max(0, Math.round(seconds))
  const mins = Math.floor(total / 60)
  const secs = total % 60
  return `${mins}:${String(secs).padStart(2, '0')}`
}

/** Total runtime → `h:mm:ss` past an hour, else `m:ss`; null/0-safe `—`. */
export function formatRuntime(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0 || Number.isNaN(seconds)) return '—'
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const mins = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  return `${mins}:${String(secs).padStart(2, '0')}`
}

/** Sum of known track durations; `null` when nothing is known. */
export function sumDurations(durations: (number | null | undefined)[]): number | null {
  const known = durations.filter(
    (d): d is number => typeof d === 'number' && !Number.isNaN(d),
  )
  if (known.length === 0) return null
  return known.reduce((a, b) => a + b, 0)
}

interface Unit {
  seconds: number
  name: string
}

const TIME_UNITS: Unit[] = [
  { seconds: 60, name: 'minute' },
  { seconds: 60 * 60, name: 'hour' },
  { seconds: 60 * 60 * 24, name: 'day' },
  { seconds: 60 * 60 * 24 * 7, name: 'week' },
  { seconds: 60 * 60 * 24 * 30, name: 'month' },
  { seconds: 60 * 60 * 24 * 365, name: 'year' },
]

/**
 * ISO timestamp → relative phrase ("just now", "yesterday", "3 weeks ago").
 * Returns `null` for missing/unparseable input.
 */
export function timeAgo(iso: string | null | undefined): string | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  const elapsed = Math.max(0, (Date.now() - then) / 1000)

  if (elapsed < 60) return 'just now'
  let divisor = 1
  let label = ''
  for (const unit of TIME_UNITS) {
    if (elapsed < unit.seconds) break
    divisor = unit.seconds
    label = unit.name
  }
  // loop always sets these for elapsed >= 60s, but keep a safe fallback
  if (!label) return 'just now'
  const count = Math.floor(elapsed / divisor)
  if (label === 'day' && count === 1) return 'yesterday'
  return `${count} ${label}${count === 1 ? '' : 's'} ago`
}

/** ISO timestamp → short absolute date ("Aug 1, 2026") for history rows. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}
