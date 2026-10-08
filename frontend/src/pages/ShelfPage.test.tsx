import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Album, Tag } from '../types'
import { ShelfPage } from './ShelfPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    listAlbums: vi.fn(),
    getTags: vi.fn(),
    updateAlbum: vi.fn(),
    getCoverUrl: vi.fn((id: number) => `/api/albums/${id}/cover`),
    getCoverBlob: vi.fn().mockResolvedValue(null),
  }
  const useAuth = vi.fn()
  class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return { api, useAuth, ApiError }
})

vi.mock('../api', () => ({ api: mocks.api, ApiError: mocks.ApiError }))
vi.mock('../auth', () => ({ useAuth: () => mocks.useAuth() }))

const baseAlbum: Album = {
  id: 1,
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  label: null,
  country: null,
  source: 'deezer',
  external_id: '302127',
  cover_url: 'https://example.com/ril.jpg',
  track_count: 8,
  favorite: true,
  note: null,
  last_played_at: null,
  tags: ['art-rock', 'summer', 'chill'],
  created_at: '2026-01-01T00:00:00Z',
}

const albums: Album[] = [
  baseAlbum,
  {
    ...baseAlbum,
    id: 2,
    title: 'Speaking in Tongues',
    year: 1983,
    favorite: false,
    tags: ['chill'],
  },
  {
    ...baseAlbum,
    id: 3,
    title: 'Fear of Music',
    year: 1979,
    favorite: false,
    tags: ['post-punk'],
  },
]

const tags: Tag[] = [
  { id: 1, name: 'chill', album_count: 2 },
  { id: 2, name: 'summer', album_count: 1 },
]

function renderShelf(initial = '/') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ShelfPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  mocks.api.listAlbums.mockReset()
  mocks.api.getTags.mockReset()
  mocks.api.updateAlbum.mockReset()
  mocks.api.listAlbums.mockResolvedValue(albums)
  mocks.api.getTags.mockResolvedValue(tags)
  mocks.useAuth.mockReturnValue(defaultAuth())
})

describe('ShelfPage', () => {
  it('renders the responsive cover grid with album metadata', async () => {
    renderShelf()
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()

    const grid = screen.getByTestId('shelf-grid')
    expect(within(grid).getByText('Fear of Music')).toBeInTheDocument()
    expect(within(grid).getAllByText('Talking Heads · 1980')).toHaveLength(1)
    expect(within(grid).getAllByText('Talking Heads · 1983')).toHaveLength(1)
    // Covers lazily point at the cached endpoint.
    expect(within(grid).getAllByRole('img')[0]).toHaveAttribute(
      'src',
      '/api/albums/1/cover',
    )
    expect(within(grid).getAllByRole('link')[0]).toHaveAttribute('href', '/album/1')
  })

  it('filters the loaded list instantly without a refetch', async () => {
    const user = userEvent.setup()
    renderShelf()
    await screen.findByText('Remain in Light')

    await user.type(screen.getByLabelText('Filter albums'), 'fear')
    expect(screen.queryByText('Remain in Light')).not.toBeInTheDocument()
    expect(screen.getByText('Fear of Music')).toBeInTheDocument()
    expect(mocks.api.listAlbums).toHaveBeenCalledTimes(1)
  })

  it('refetches server-side when a tag chip is picked', async () => {
    const user = userEvent.setup()
    renderShelf()
    await screen.findByText('Remain in Light')

    await user.click(screen.getByRole('button', { name: /chill/ }))
    await waitFor(() =>
      expect(mocks.api.listAlbums).toHaveBeenCalledWith(
        expect.objectContaining({ tag: 'chill' }),
      ),
    )
  })

  it('relays the sort selector to the API', async () => {
    const user = userEvent.setup()
    renderShelf()
    await screen.findByText('Remain in Light')

    await user.selectOptions(screen.getByLabelText('Sort albums'), 'year')
    await waitFor(() =>
      expect(mocks.api.listAlbums).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'year' }),
      ),
    )
  })

  it('toggles favorites-only from the toolbar', async () => {
    const user = userEvent.setup()
    renderShelf()
    await screen.findByText('Remain in Light')

    await user.click(screen.getByRole('button', { name: 'Favorites' }))
    await waitFor(() =>
      expect(mocks.api.listAlbums).toHaveBeenCalledWith(
        expect.objectContaining({ favorite: true }),
      ),
    )
  })

  it('toggles a favorite from the card star and updates in place', async () => {
    const user = userEvent.setup()
    const demoted = { ...baseAlbum, favorite: false }
    mocks.api.updateAlbum.mockResolvedValue(demoted)
    renderShelf()
    await screen.findByText('Remain in Light')

    await user.click(
      screen.getByRole('button', { name: 'Remove Remain in Light from favorites' }),
    )
    await waitFor(() =>
      expect(mocks.api.updateAlbum).toHaveBeenCalledWith(1, { favorite: false }),
    )
    expect(
      await screen.findByRole('button', { name: 'Add Remain in Light to favorites' }),
    ).toBeInTheDocument()
  })

  it('shows the empty state with a CTA when the shelf has no records', async () => {
    mocks.api.listAlbums.mockResolvedValue([])
    renderShelf()
    expect(await screen.findByText('Shelf is empty — add your first record')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add your first record' })).toHaveAttribute(
      'href',
      '/add',
    )
  })

  it('respects an incoming ?tag= shelf link', async () => {
    renderShelf('/?tag=summer')
    await waitFor(() =>
      expect(mocks.api.listAlbums).toHaveBeenCalledWith(
        expect.objectContaining({ tag: 'summer' }),
      ),
    )
  })

  it('surfaces load errors with a retry action', async () => {
    mocks.api.listAlbums.mockRejectedValue(new mocks.ApiError(500, 'Server exploded'))
    renderShelf()
    expect(await screen.findByText('Server exploded')).toBeInTheDocument()
  })
})