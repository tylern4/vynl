import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Album, Tag, TrackSearchResult } from '../types'
import { FindPage } from './FindPage'

const mocks = vi.hoisted(() => {
  const api = {
    getTags: vi.fn(),
    searchTracks: vi.fn(),
    listAlbums: vi.fn(),
    getCoverUrl: vi.fn((id: number) => `/api/albums/${id}/cover`),
    getCoverBlob: vi.fn().mockResolvedValue(null),
  }
  class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return { api, ApiError }
})

vi.mock('../api', () => ({ api: mocks.api, ApiError: mocks.ApiError }))

const tags: Tag[] = [
  { id: 1, name: 'summer', album_count: 3 },
  { id: 2, name: 'winter', album_count: 1 },
]

const track: TrackSearchResult = {
  id: 41,
  title: 'Once in a Lifetime',
  duration_seconds: 259,
  position: 4,
  album: {
    id: 5,
    title: 'Remain in Light',
    artist: 'Talking Heads',
    year: 1980,
    cover_url: null,
  },
}

const album: Album = {
  id: 5,
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  label: null,
  country: null,
  source: 'deezer',
  external_id: '302127',
  cover_url: 'https://example.com/ril.jpg',
  track_count: 8,
  favorite: false,
  note: null,
  last_played_at: null,
  tags: ['summer'],
  created_at: '2026-01-01T00:00:00Z',
}

function renderFind() {
  return render(
    <MemoryRouter>
      <FindPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.api.getTags.mockReset()
  mocks.api.searchTracks.mockReset()
  mocks.api.listAlbums.mockReset()
  mocks.api.getTags.mockResolvedValue(tags)
  mocks.api.searchTracks.mockResolvedValue([])
  mocks.api.listAlbums.mockResolvedValue([])
})

describe('FindPage', () => {
  it('shows songs and albums sections for a query', async () => {
    const user = userEvent.setup()
    mocks.api.searchTracks.mockResolvedValue([track])
    mocks.api.listAlbums.mockResolvedValue([album])
    renderFind()

    await user.type(screen.getByLabelText('Search your library'), 'once')
    expect(await screen.findByText('Once in a Lifetime')).toBeInTheDocument()
    await waitFor(() => expect(mocks.api.searchTracks).toHaveBeenCalledWith('once'))
    await waitFor(() =>
      expect(mocks.api.listAlbums).toHaveBeenCalledWith({ q: 'once' }),
    )

    expect(screen.getByRole('heading', { name: 'Songs (1)' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Albums (1)' })).toBeInTheDocument()

    // Song rows link through to the album detail page.
    const songLink = screen.getByRole('link', { name: /Once in a Lifetime/ })
    expect(songLink).toHaveAttribute('href', '/album/5')
    expect(songLink).toHaveTextContent('Talking Heads · Remain in Light · 1980')
    expect(songLink).toHaveTextContent('4:19')
  })

  it('surfaces matching tags that jump to a filtered shelf', async () => {
    const user = userEvent.setup()
    renderFind()

    await user.type(screen.getByLabelText('Search your library'), 'sum')
    const chip = await screen.findByRole('link', { name: /summer/ })
    expect(chip).toHaveAttribute('href', '/?tag=summer')
    expect(screen.getByRole('heading', { name: 'Tags (1)' })).toBeInTheDocument()
  })

  it('shows the initial empty state', () => {
    renderFind()
    expect(
      screen.getByRole('heading', { name: 'Search your library' }),
    ).toBeInTheDocument()
  })

  it('shows a no-results state', async () => {
    const user = userEvent.setup()
    renderFind()

    await user.type(screen.getByLabelText('Search your library'), 'zzz')
    expect(await screen.findByText(/Nothing matched/)).toBeInTheDocument()
  })

  it('shows a section error and retries the same query', async () => {
    const user = userEvent.setup()
    mocks.api.searchTracks
      .mockRejectedValueOnce(new mocks.ApiError(500, 'songs exploded'))
      .mockResolvedValue([track])
    renderFind()

    await user.type(screen.getByLabelText('Search your library'), 'once')
    expect(await screen.findByText(/Songs unavailable/)).toBeInTheDocument()
    expect(screen.getByText(/songs exploded/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry songs' }))
    expect(await screen.findByText('Once in a Lifetime')).toBeInTheDocument()
  })
})