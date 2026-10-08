import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Album } from '../types'
import { AlbumCard } from './AlbumCard'

const album: Album = {
  id: 7,
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  label: 'Sire',
  country: 'US',
  source: 'deezer',
  external_id: '302127',
  cover_url: 'https://example.com/ril.jpg',
  track_count: 8,
  favorite: false,
  note: null,
  last_played_at: null,
  tags: ['art-rock', 'summer'],
  created_at: '2026-01-01T00:00:00Z',
}

function renderCard(props: Partial<Parameters<typeof AlbumCard>[0]> = {}) {
  return render(
    <MemoryRouter>
      <AlbumCard album={album} {...props} />
    </MemoryRouter>,
  )
}

describe('AlbumCard', () => {
  it('renders title, artist · year, and the first tags', () => {
    renderCard()
    expect(screen.getByText('Remain in Light')).toBeInTheDocument()
    expect(screen.getByText('Talking Heads · 1980')).toBeInTheDocument()
    expect(screen.getByText('art-rock')).toBeInTheDocument()
    expect(screen.getByText('summer')).toBeInTheDocument()
  })

  it('links to the album detail page', () => {
    renderCard()
    expect(screen.getByRole('link', { name: /Remain in Light/ })).toHaveAttribute(
      'href',
      '/album/7',
    )
  })

  it('shows a favorite star that reports the current state', async () => {
    const user = userEvent.setup()
    const onToggleFavorite = vi.fn()
    renderCard({ onToggleFavorite })
    const star = screen.getByRole('button', { name: 'Add Remain in Light to favorites' })
    expect(star).toHaveAttribute('aria-pressed', 'false')
    await user.click(star)
    expect(onToggleFavorite).toHaveBeenCalledWith(album)
  })

  it('flips the star label when already favorited', () => {
    renderCard({ album: { ...album, favorite: true }, onToggleFavorite: vi.fn() })
    const star = screen.getByRole('button', { name: 'Remove Remain in Light from favorites' })
    expect(star).toHaveAttribute('aria-pressed', 'true')
  })
})