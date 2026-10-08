import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Album, SearchResult } from '../types'
import { AddAlbumPage } from './AddAlbumPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    searchAlbums: vi.fn(),
    importAlbum: vi.fn(),
    previewAlbum: vi.fn(),
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

const deezerResult: SearchResult = {
  source: 'deezer',
  external_id: '302127',
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  track_count: 8,
  cover_url: 'https://example.com/ril.jpg',
  label: 'Sire',
}

const mbResult: SearchResult = {
  source: 'musicbrainz',
  external_id: 'mbid-123',
  title: 'Speaking in Tongues',
  artist: 'Talking Heads',
  year: 1983,
  track_count: 9,
  cover_url: null,
  label: null,
}

const importedAlbum: Album = {
  id: 42,
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
  tags: [],
  created_at: '2026-01-01T00:00:00Z',
}

function renderAdd() {
  return render(
    <MemoryRouter>
      <AddAlbumPage />
    </MemoryRouter>,
  )
}

async function searchFor(user: ReturnType<typeof userEvent.setup>, q: string) {
  await user.type(screen.getByLabelText('Search for an album'), q)
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  mocks.api.searchAlbums.mockReset()
  mocks.api.importAlbum.mockReset()
  mocks.api.previewAlbum.mockReset()
  mocks.useAuth.mockReturnValue(defaultAuth())
})

describe('AddAlbumPage', () => {
  it('debounces the search and shows merged results with source badges', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([deezerResult, mbResult])
    renderAdd()

    await searchFor(user, 'talking heads')
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()
    await waitFor(() =>
      expect(mocks.api.searchAlbums).toHaveBeenCalledWith('talking heads'),
    )
    expect(screen.getByText('Talking Heads · 1980 · 8 tracks')).toBeInTheDocument()

    // Source badges live on the result rows (attribution line also names providers).
    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Deezer')).toBeInTheDocument()
    expect(within(rows[1]).getByText('MusicBrainz')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Import/ })).toHaveLength(2)
  })

  it('shows provider-attribution and an initial empty state', () => {
    renderAdd()
    expect(screen.getByText(/Search results come from/)).toBeInTheDocument()
    expect(screen.getByText('MusicBrainz')).toBeInTheDocument()
    expect(screen.getByText('Deezer')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Find your next record' })).toBeInTheDocument()
  })

  it('imports on click and links to the new album', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([deezerResult])
    mocks.api.importAlbum.mockResolvedValue(importedAlbum)
    renderAdd()

    await searchFor(user, 'remain')
    const button = await screen.findByRole('button', { name: /Import/ })
    await user.click(button)
    await waitFor(() =>
      expect(mocks.api.importAlbum).toHaveBeenCalledWith({
        source: 'deezer',
        external_id: '302127',
      }),
    )
    const link = await screen.findByRole('link', { name: 'On your shelf — view' })
    expect(link).toHaveAttribute('href', '/album/42')
  })

  it('maps a 409 to an already-added state linking the existing album', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([deezerResult])
    mocks.api.importAlbum.mockRejectedValue(
      new mocks.ApiError(409, 'Album already in your shelf (id=42)'),
    )
    renderAdd()

    await searchFor(user, 'remain')
    const button = await screen.findByRole('button', { name: /Import/ })
    await user.click(button)
    const link = await screen.findByRole('link', { name: 'View album' })
    expect(link).toHaveAttribute('href', '/album/42')
  })

  it('surfaces provider errors inline and retries the same row', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([deezerResult])
    mocks.api.importAlbum.mockRejectedValue(
      new mocks.ApiError(502, 'Provider error: deezer hung up'),
    )
    renderAdd()

    await searchFor(user, 'remain')
    const button = await screen.findByRole('button', { name: /Import/ })
    await user.click(button)
    expect(await screen.findByText('Provider error: deezer hung up')).toBeInTheDocument()
    // Failure guidance tells the user what to do next.
    expect(screen.getByText(/music service may be briefly unavailable/)).toBeInTheDocument()

    mocks.api.importAlbum.mockResolvedValue(importedAlbum)
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(mocks.api.importAlbum).toHaveBeenCalledTimes(2))
    expect(
      await screen.findByRole('link', { name: 'On your shelf — view' }),
    ).toBeInTheDocument()
  })

  it('shows a no-results state', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([])
    renderAdd()

    await searchFor(user, 'zzz')
    expect(await screen.findByText(/Nothing found for “zzz”/)).toBeInTheDocument()
  })

  it('clicking a result title opens the import-preview modal', async () => {
    const user = userEvent.setup()
    mocks.api.searchAlbums.mockResolvedValue([deezerResult])
    mocks.api.previewAlbum.mockResolvedValue({
      source: 'deezer',
      external_id: '302127',
      title: 'Remain in Light',
      artist: 'Talking Heads',
      year: 1980,
      label: 'Sire',
      country: 'US',
      cover_url: 'https://example.com/ril.jpg',
      track_count: 1,
      tracks: [{ position: 1, title: 'Born Under Punches', duration_seconds: 349 }],
      source_breakdown: {
        metadata_source: 'musicbrainz',
        tracklist_source: 'deezer',
        artwork_source: 'deezer',
      },
      tracklists_by_source: {
        deezer: [{ position: 1, title: 'Born Under Punches', duration_seconds: 349 }],
      },
    })
    renderAdd()

    await searchFor(user, 'remain')
    const titleButton = await screen.findByRole('button', {
      name: 'Preview Remain in Light by Talking Heads',
    })
    await user.click(titleButton)

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('Remain in Light')
    await waitFor(() =>
      expect(mocks.api.previewAlbum).toHaveBeenCalledWith({
        source: 'deezer',
        external_id: '302127',
      }),
    )
    expect(await screen.findByText('Born Under Punches')).toBeInTheDocument()
    // One modal at a time — the import fast path for the row stays available.
    expect(screen.getByRole('button', { name: /Import this album/ })).toBeInTheDocument()

    // Esc closes the modal again.
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})