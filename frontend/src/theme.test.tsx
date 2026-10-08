import { beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  PALETTES,
  PALETTE_STORAGE_KEY,
  applyPalette,
  applyTheme,
  getInitialPalette,
  getInitialTheme,
  useTheme,
} from './theme'

function stubMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string): MediaQueryList => ({
      matches,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  })
}

beforeEach(() => {
  localStorage.clear()
  stubMatchMedia(false)
  delete document.documentElement.dataset.theme
  delete document.documentElement.dataset.palette
})

describe('getInitialTheme', () => {
  it('prefers the stored theme', () => {
    localStorage.setItem('vynl_theme', 'dark')
    expect(getInitialTheme()).toBe('dark')
    localStorage.setItem('vynl_theme', 'light')
    expect(getInitialTheme()).toBe('light')
  })

  it('falls back to the system preference', () => {
    stubMatchMedia(false)
    expect(getInitialTheme()).toBe('light')
    stubMatchMedia(true)
    expect(getInitialTheme()).toBe('dark')
  })
})

describe('applyTheme', () => {
  it('sets data-theme on the document element', () => {
    applyTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})

describe('getInitialPalette', () => {
  it('defaults to the default palette', () => {
    expect(getInitialPalette()).toBe('default')
  })

  it('prefers the stored palette', () => {
    localStorage.setItem(PALETTE_STORAGE_KEY, 'cyberpunk')
    expect(getInitialPalette()).toBe('cyberpunk')
  })

  it('falls back for unknown stored values', () => {
    localStorage.setItem(PALETTE_STORAGE_KEY, 'hotdog-stand')
    expect(getInitialPalette()).toBe('default')
  })
})

describe('applyPalette', () => {
  it('sets data-palette on the document element', () => {
    applyPalette('citypop')
    expect(document.documentElement.dataset.palette).toBe('citypop')
    applyPalette('default')
    expect(document.documentElement.dataset.palette).toBe('default')
  })
})

describe('PALETTES catalog', () => {
  it('exposes all 8 palettes with the FOUC-guard axis values', () => {
    expect(PALETTES.map((p) => p.id)).toEqual([
      'default',
      'citypop',
      'cyberpunk',
      'recordshop',
      'hippie',
      'deathmetal',
      'punk',
      'classical',
    ])
  })

  it('gives every palette a label and light/dark preview swatches', () => {
    for (const p of PALETTES) {
      expect(p.label).toBeTruthy()
      for (const swatches of [p.light, p.dark]) {
        expect(swatches.accent).toMatch(/^#[0-9a-fA-F]{6}$/)
        expect(swatches.bg).toMatch(/^#[0-9a-fA-F]{6}$/)
        expect(swatches.surface).toMatch(/^#[0-9a-fA-F]{6}$/)
        expect(swatches.text).toMatch(/^#[0-9a-fA-F]{6}$/)
      }
    }
  })
})

describe('useTheme', () => {
  it('starts from stored theme and palette', () => {
    localStorage.setItem('vynl_theme', 'dark')
    localStorage.setItem(PALETTE_STORAGE_KEY, 'punk')
    const { result } = renderHook(() => useTheme())
    expect(result.current.mode).toBe('dark')
    expect(result.current.palette).toBe('punk')
  })

  it('toggles the mode and persists it', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.mode).toBe('light')

    act(() => result.current.toggleMode())
    expect(result.current.mode).toBe('dark')
    expect(localStorage.getItem('vynl_theme')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')

    act(() => result.current.toggleMode())
    expect(result.current.mode).toBe('light')
    expect(localStorage.getItem('vynl_theme')).toBe('light')
  })

  it('sets a palette, applies it to <html> and persists it', () => {
    const { result } = renderHook(() => useTheme())
    expect(document.documentElement.dataset.palette).toBe('default')

    act(() => result.current.setPalette('recordshop'))
    expect(result.current.palette).toBe('recordshop')
    expect(document.documentElement.dataset.palette).toBe('recordshop')
    expect(localStorage.getItem(PALETTE_STORAGE_KEY)).toBe('recordshop')
  })

  it('setMode applies and persists the mode axis', () => {
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setMode('dark'))
    expect(result.current.mode).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('vynl_theme')).toBe('dark')
  })
})