import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDuration,
  formatRuntime,
  sumDurations,
  timeAgo,
} from './format'

describe('formatDuration', () => {
  it('formats seconds as m:ss', () => {
    expect(formatDuration(349)).toBe('5:49')
    expect(formatDuration(60)).toBe('1:00')
    expect(formatDuration(7)).toBe('0:07')
    expect(formatDuration(725)).toBe('12:05')
  })

  it('is null-safe', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
  })
})

describe('formatRuntime', () => {
  it('formats total runtime, switching to h:mm:ss past an hour', () => {
    expect(formatRuntime(626)).toBe('10:26')
    expect(formatRuntime(3661)).toBe('1:01:01')
    expect(formatRuntime(0)).toBe('—')
    expect(formatRuntime(null)).toBe('—')
  })
})

describe('sumDurations', () => {
  it('sums known durations and ignores nulls', () => {
    expect(sumDurations([349, 277, null])).toBe(626)
  })

  it('returns null when nothing is known', () => {
    expect(sumDurations([null, null])).toBeNull()
    expect(sumDurations([])).toBeNull()
  })
})

describe('timeAgo', () => {
  it('produces relative phrases', () => {
    const now = Date.now()
    expect(timeAgo(new Date(now - 10_000).toISOString())).toBe('just now')
    expect(timeAgo(new Date(now - 3 * 60_000).toISOString())).toBe('3 minutes ago')
    expect(timeAgo(new Date(now - 26 * 60_000).toISOString())).toBe('26 minutes ago')
    expect(timeAgo(new Date(now - 2 * 3600_000).toISOString())).toBe('2 hours ago')
    expect(timeAgo(new Date(now - 3600_000).toISOString())).toBe('1 hour ago')
    expect(timeAgo(new Date(now - 86400_000).toISOString())).toBe('yesterday')
    expect(timeAgo(new Date(now - 21 * 86400_000).toISOString())).toBe('3 weeks ago')
    expect(timeAgo(new Date(now - 40 * 86400_000).toISOString())).toBe('1 month ago')
    expect(timeAgo(new Date(now - 400 * 86400_000).toISOString())).toBe('1 year ago')
  })

  it('returns null for missing/unparseable input', () => {
    expect(timeAgo(null)).toBeNull()
    expect(timeAgo(undefined)).toBeNull()
    expect(timeAgo('not-a-date')).toBeNull()
  })
})

describe('formatDate', () => {
  it('formats a short absolute date', () => {
    expect(formatDate('2026-08-01T22:14:00Z')).toMatch(/Aug 1, 2026/)
    expect(formatDate(null)).toBe('—')
  })
})