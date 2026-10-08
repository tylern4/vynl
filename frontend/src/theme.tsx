import { useCallback, useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

/**
 * Palette axis: a second, independent axis from the light/dark mode. Selected
 * via the `data-palette` attribute on `<html>` (kept in sync with
 * `styles.css`, which holds every palette's full token block for light and
 * dark). Persisted under `vynl_palette`; defaults to `default`.
 */
export type PaletteName =
  | 'default'
  | 'citypop'
  | 'cyberpunk'
  | 'recordshop'
  | 'hippie'
  | 'deathmetal'
  | 'punk'
  | 'classical'

/** The four token colors rendered as live swatches in the settings grid. */
export interface PaletteSwatches {
  accent: string
  bg: string
  surface: string
  text: string
}

export interface Palette {
  id: PaletteName
  label: string
  light: PaletteSwatches
  dark: PaletteSwatches
}

const THEME_STORAGE_KEY = 'vynl_theme'
export const PALETTE_STORAGE_KEY = 'vynl_palette'

/**
 * Catalog of every palette. The swatch hexes mirror the token blocks in
 * `styles.css` — keep the two files in sync (the settings grid renders
 * previews from these values; the real theming comes from CSS).
 */
export const PALETTES: Palette[] = [
  {
    id: 'default',
    label: 'Default',
    light: { accent: '#b85c1e', bg: '#f6f5f2', surface: '#ffffff', text: '#2b2a26' },
    dark: { accent: '#b85c1e', bg: '#18181c', surface: '#212126', text: '#ece9e4' },
  },
  {
    id: 'citypop',
    label: 'City pop',
    light: { accent: '#4c5dd7', bg: '#fbf0f4', surface: '#ffffff', text: '#2a1c33' },
    dark: { accent: '#6b5ce0', bg: '#1d0225', surface: '#2a0b35', text: '#f6eff8' },
  },
  {
    id: 'cyberpunk',
    label: 'Cyberpunk',
    light: { accent: '#c01a86', bg: '#e8edf7', surface: '#ffffff', text: '#0b0d17' },
    dark: { accent: '#c01a86', bg: '#0b0d17', surface: '#141726', text: '#c9d1d9' },
  },
  {
    id: 'recordshop',
    label: 'Record shop',
    light: { accent: '#b34e0e', bg: '#f4ede0', surface: '#fdfaf2', text: '#2e2418' },
    dark: { accent: '#b34e0e', bg: '#211712', surface: '#2c201a', text: '#ece0cf' },
  },
  {
    id: 'hippie',
    label: '70s hippie',
    light: { accent: '#bc4a2e', bg: '#faf3e4', surface: '#fffcf4', text: '#33261a' },
    dark: { accent: '#bc4a2e', bg: '#2b1c10', surface: '#38261a', text: '#f2e9d8' },
  },
  {
    id: 'deathmetal',
    label: 'Death metal',
    light: { accent: '#8e0f1e', bg: '#f1ece6', surface: '#ffffff', text: '#191512' },
    dark: { accent: '#a3121f', bg: '#0d0c0b', surface: '#171412', text: '#ece4d8' },
  },
  {
    id: 'punk',
    label: 'Punk',
    light: { accent: '#c81d1d', bg: '#f5f3ec', surface: '#ffffff', text: '#16130e' },
    dark: { accent: '#c81d1d', bg: '#0b0b0a', surface: '#151412', text: '#f3f1ea' },
  },
  {
    id: 'classical',
    label: 'Classical',
    light: { accent: '#14213d', bg: '#f4f0e7', surface: '#ffffff', text: '#14213d' },
    dark: { accent: '#d4a92e', bg: '#1a1e2e', surface: '#232a3d', text: '#f5f1e6' },
  },
]

/** All valid palette ids, for validating localStorage reads. */
const PALETTE_IDS: ReadonlySet<string> = new Set(PALETTES.map((p) => p.id))

export function getInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

/** Reads `vynl_palette`, falling back to `default` for anything unknown. */
export function getInitialPalette(): PaletteName {
  const stored = localStorage.getItem(PALETTE_STORAGE_KEY)
  return stored && PALETTE_IDS.has(stored) ? (stored as PaletteName) : 'default'
}

export function applyPalette(palette: PaletteName) {
  document.documentElement.dataset.palette = palette
}

export function useTheme() {
  const [mode, setMode] = useState<Theme>(getInitialTheme)
  const [palette, setPalette] = useState<PaletteName>(getInitialPalette)

  useEffect(() => {
    applyTheme(mode)
    localStorage.setItem(THEME_STORAGE_KEY, mode)
  }, [mode])

  useEffect(() => {
    applyPalette(palette)
    localStorage.setItem(PALETTE_STORAGE_KEY, palette)
  }, [palette])

  const toggleMode = useCallback(() => {
    setMode((m) => (m === 'dark' ? 'light' : 'dark'))
  }, [])

  return { mode, palette, setMode, setPalette, toggleMode }
}