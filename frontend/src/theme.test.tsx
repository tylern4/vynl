import { beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { applyTheme, getInitialTheme, useTheme } from './theme'

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

describe('useTheme', () => {
  it('toggles and persists the theme', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')

    act(() => result.current.toggle())
    expect(result.current.theme).toBe('dark')
    expect(localStorage.getItem('vynl_theme')).toBe('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')

    act(() => result.current.toggle())
    expect(result.current.theme).toBe('light')
    expect(localStorage.getItem('vynl_theme')).toBe('light')
  })

  it('starts from the stored theme', () => {
    localStorage.setItem('vynl_theme', 'dark')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })
})
