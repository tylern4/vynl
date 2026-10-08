import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Album, Tag } from '../types'
import { AlbumDetailPage } from './AlbumDetailPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    getAlbum: vi.fn(),
    listPlays: vi.fn(),
    getTags: vi.fn(),
    updateAlbum: vi.fn(),
    setAlbumTags: vi.fn(),
    logPlay: vi.fn(),
    deletePlay: vi.fn(),
    deleteAlbum: vi.fn(),
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
  track_count: 3,
  favorite: false,
  note: null,
  last_played_at: null,
  tags: ['art-rock'],
  created_at: '2026-01-01T00:00:00Z',
  tracks: [
    { id: 1, position: 1, title: 'Born Under Punches', duration_seconds: 349 },
    { id: 2, position: 2, title: 'Crosseyed and Painless', duration_seconds: 277 },
    { id: 3, position: 3, title: 'The Great Curve', duration_seconds: null },
  ],
}

const allTags: Tag[] = [
  { id: 1, name: 'chill', album_count: 2 },
  { id: 2, name: 'summer', album_count: 1 },
]

function renderDetail(albumId = 7) {
  return render(
    <MemoryRouter initialEntries={[`/album/${albumId}`]}>
      <Routes>
        <Route path="/" element={<div>Shelf home</div>} />
        <Route path="/album/:id" element={<AlbumDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  Object.values(mocks.api).forEach((fn) => fn.mockClear())
  mocks.api.getCoverBlob.mockResolvedValue(null)
  mocks.api.getAlbum.mockResolvedValue(album)
  mocks.api.listPlays.mockResolvedValue([])
  mocks.api.getTags.mockResolvedValue(allTags)
  mocks.useAuth.mockReturnValue(defaultAuth())
})

describe('AlbumDetailPage', () => {
  it('renders artwork, metadata, and the tracklist with durations and total', async () => {
    renderDetail()
    expect(
      await screen.findByRole('heading', { name: 'Remain in Light' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Talking Heads')).toBeInTheDocument()
    expect(screen.getByText('1980')).toBeInTheDocument()
    expect(screen.getByText('Sire')).toBeInTheDocument()
    expect(screen.getByText('US')).toBeInTheDocument()
    expect(screen.getByText('Deezer')).toBeInTheDocument()
    expect(screen.getByText('Never spun')).toBeInTheDocument()

    expect(screen.getByText('Born Under Punches')).toBeInTheDocument()
    expect(screen.getByText('5:49')).toBeInTheDocument()
    expect(screen.getByText('4:37')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument() // null duration
    expect(screen.getByText('3 tracks')).toBeInTheDocument()
    expect(screen.getByText('10:26')).toBeInTheDocument()
  })

  it('shows a 404 state', async () => {
    mocks.api.getAlbum.mockRejectedValue(new mocks.ApiError(404, 'Album not found'))
    renderDetail()
    expect(
      await screen.findByRole('heading', { name: 'Album not found' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to shelf' })).toBeInTheDocument()
  })

  it('shows an error state with retry for other failures', async () => {
    mocks.api.getAlbum.mockRejectedValue(new mocks.ApiError(500, 'boom'))
    renderDetail()
    expect(
      await screen.findByRole('heading', { name: 'Something went wrong' }),
    ).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()

    mocks.api.getAlbum.mockResolvedValue(album)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Born Under Punches')).toBeInTheDocument()
  })

  it('toggles favorite via PATCH', async () => {
    const user = userEvent.setup()
    mocks.api.updateAlbum.mockResolvedValue({ ...album, favorite: true })
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'Favorite' }))
    await waitFor(() =>
      expect(mocks.api.updateAlbum).toHaveBeenCalledWith(7, { favorite: true }),
    )
    expect(
      await screen.findByRole('button', { name: 'Favorited' }),
    ).toBeInTheDocument()
  })

  it('saves a personal note', async () => {
    const user = userEvent.setup()
    mocks.api.updateAlbum.mockResolvedValue({ ...album, note: 'first pressing' })
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.type(screen.getByLabelText('Personal note'), 'first pressing')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() =>
      expect(mocks.api.updateAlbum).toHaveBeenCalledWith(7, { note: 'first pressing' }),
    )
    expect(await screen.findByText('Saved.')).toBeInTheDocument()
  })

  it('adds a tag from the autocomplete suggestions', async () => {
    const user = userEvent.setup()
    mocks.api.setAlbumTags.mockResolvedValue({ ...album, tags: ['art-rock', 'chill'] })
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.type(screen.getByLabelText('Add a tag'), 'ch')
    await user.click(await screen.findByRole('button', { name: 'chill' }))
    await waitFor(() =>
      expect(mocks.api.setAlbumTags).toHaveBeenCalledWith(7, ['art-rock', 'chill']),
    )
  })

  it('removes a tag from the chips', async () => {
    const user = userEvent.setup()
    mocks.api.setAlbumTags.mockResolvedValue({ ...album, tags: [] })
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'Remove tag art-rock' }))
    await waitFor(() =>
      expect(mocks.api.setAlbumTags).toHaveBeenCalledWith(7, []),
    )
  })

  it('logs a spin and shows the play history', async () => {
    const user = userEvent.setup()
    const playedAt = new Date(Date.now() - 21 * 86400_000).toISOString()
    mocks.api.logPlay.mockResolvedValue({ ...album, last_played_at: playedAt })
    mocks.api.listPlays.mockResolvedValue([{ id: 11, played_at: playedAt }])
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'I spun this' }))
    await waitFor(() => expect(mocks.api.logPlay).toHaveBeenCalledWith(7))
    expect(await screen.findByText('Last spun: 3 weeks ago')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete play' })).toBeInTheDocument()
  })

  it('deletes a play from the history', async () => {
    const user = userEvent.setup()
    mocks.api.listPlays.mockResolvedValue([
      { id: 11, played_at: new Date().toISOString() },
    ])
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'Delete play' }))
    await waitFor(() => expect(mocks.api.deletePlay).toHaveBeenCalledWith(7, 11))
  })

  it('removes the album after an inline confirmation', async () => {
    const user = userEvent.setup()
    mocks.api.deleteAlbum.mockResolvedValue(undefined)
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'Remove from shelf' }))
    expect(screen.getByText(/from your shelf/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes, remove it' }))
    await waitFor(() => expect(mocks.api.deleteAlbum).toHaveBeenCalledWith(7))
    expect(await screen.findByText('Shelf home')).toBeInTheDocument()
  })

  it('cancels the remove confirmation', async () => {
    const user = userEvent.setup()
    renderDetail()
    await screen.findByRole('heading', { name: 'Remain in Light' })

    await user.click(screen.getByRole('button', { name: 'Remove from shelf' }))
    await user.click(screen.getByRole('button', { name: 'Keep it' }))
    expect(mocks.api.deleteAlbum).not.toHaveBeenCalled()
  })
})