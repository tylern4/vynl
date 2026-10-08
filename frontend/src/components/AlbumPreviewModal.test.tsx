import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { AlbumPreview, SearchResult } from '../types'
import { AlbumPreviewModal } from './AlbumPreviewModal'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    previewAlbum: vi.fn(),
    importAlbum: vi.fn(),
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

const row: SearchResult = {
  source: 'deezer',
  external_id: '302127',
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  track_count: 8,
  cover_url: 'https://example.com/ril.jpg',
  label: 'Sire',
}

const deezerTracks = [
  { position: 1, title: 'Born Under Punches', duration_seconds: 349 },
  { position: 2, title: 'Crosseyed and Painless', duration_seconds: 285 },
]

const musicbrainzTracks = [
  { position: 1, title: 'Born Under Punches', duration_seconds: 349 },
  { position: 2, title: 'Crosseyed and Painless', duration_seconds: 285 },
  { position: 3, title: 'The Great Curve', duration_seconds: 263 },
]

const mergedPreview: AlbumPreview = {
  source: 'deezer',
  external_id: '302127',
  title: 'Remain in Light',
  artist: 'Talking Heads',
  year: 1980,
  label: 'Sire',
  country: 'US',
  cover_url: 'https://example.com/ril.jpg',
  track_count: 2,
  tracks: deezerTracks,
  source_breakdown: {
    metadata_source: 'musicbrainz',
    tracklist_source: 'deezer',
    artwork_source: 'cover_art_archive',
  },
  tracklists_by_source: {
    deezer: deezerTracks,
    musicbrainz: musicbrainzTracks,
  },
}

function renderModal() {
  const onClose = vi.fn()
  const utils = render(
    <MemoryRouter>
      <AlbumPreviewModal row={row} onClose={onClose} />
    </MemoryRouter>,
  )
  return { ...utils, onClose }
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  mocks.api.previewAlbum.mockReset()
  mocks.api.importAlbum.mockReset()
  mocks.useAuth.mockReturnValue(defaultAuth())
})

describe('AlbumPreviewModal', () => {
  it('renders cover, metadata, tracklist, and breakdown badges', async () => {
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    renderModal()

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName('Remain in Light')
    // The dialog shell renders before the preview resolves — wait for actual
    // preview content before asserting on anything response-dependent.
    await screen.findByText('Born Under Punches')
    expect(screen.getByAltText('Remain in Light cover')).toBeInTheDocument()
    expect(screen.getByText('Talking Heads')).toBeInTheDocument()
    expect(screen.getByText('1980')).toBeInTheDocument()
    expect(screen.getByText('Sire')).toBeInTheDocument()
    expect(screen.getByText('US')).toBeInTheDocument()
    // track count appears in the meta line and the tracklist footer.
    expect(screen.getAllByText('2 tracks').length).toBeGreaterThan(0)

    // Tracklist with detail-page duration formatting.
    expect(screen.getByText('Born Under Punches')).toBeInTheDocument()
    expect(screen.getByText('5:49')).toBeInTheDocument()
    expect(screen.getByText('4:45')).toBeInTheDocument()

    // Per-part source breakdown badges.
    expect(screen.getByText('Metadata from MusicBrainz')).toBeInTheDocument()
    expect(screen.getByText('Tracklist from Deezer')).toBeInTheDocument()
    expect(screen.getByText('Artwork from Cover Art Archive')).toBeInTheDocument()

    // The row's own source badge.
    expect(screen.getByText('Deezer')).toBeInTheDocument()
  })

  it('offers a tracklist-source toggle and switches between tracklists', async () => {
    const user = userEvent.setup()
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    renderModal()
    await screen.findByRole('dialog')

    // Preferred source (deezer) is preselected; its 2-track list is shown.
    // Wait for the group — it renders only once the preview response arrives.
    const group = await screen.findByRole('group', { name: 'Tracklist source' })
    const deezer = within(group).getByRole('button', { name: 'Deezer · 2 tracks' })
    const mb = within(group).getByRole('button', { name: 'MusicBrainz · 3 tracks' })
    expect(deezer).toHaveAttribute('aria-pressed', 'true')
    expect(mb).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText('The Great Curve')).not.toBeInTheDocument()

    await user.click(mb)
    expect(mb).toHaveAttribute('aria-pressed', 'true')
    expect(deezer).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('The Great Curve')).toBeInTheDocument()
    expect(screen.getByText('Showing the MusicBrainz pressing.')).toBeInTheDocument()

    // Selection persists in state — switching back restores the Deezer list.
    await user.click(deezer)
    expect(screen.queryByText('The Great Curve')).not.toBeInTheDocument()
    expect(screen.getByText('Showing the Deezer pressing.')).toBeInTheDocument()
  })

  it('imports via the existing api.importAlbum and offers a view link', async () => {
    const user = userEvent.setup()
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    mocks.api.importAlbum.mockResolvedValue({ id: 42 })
    renderModal()
    await screen.findByRole('dialog')

    await user.click(screen.getByRole('button', { name: /Import this album/ }))
    await waitFor(() =>
      expect(mocks.api.importAlbum).toHaveBeenCalledWith({
        source: 'deezer',
        external_id: '302127',
      }),
    )
    const link = await screen.findByRole('link', { name: 'On your shelf — view' })
    expect(link).toHaveAttribute('href', '/album/42')
  })

  it('maps an import 409 to the already-in-shelf link', async () => {
    const user = userEvent.setup()
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    mocks.api.importAlbum.mockRejectedValue(
      new mocks.ApiError(409, 'Album already in your shelf (id=42)'),
    )
    renderModal()
    await screen.findByRole('dialog')

    await user.click(screen.getByRole('button', { name: /Import this album/ }))
    const link = await screen.findByRole('link', { name: 'View album' })
    expect(link).toHaveAttribute('href', '/album/42')
    expect(mocks.api.importAlbum).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape, backdrop click, and the close button', async () => {
    const user = userEvent.setup()
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    const { onClose, rerender } = renderModal()
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)

    // Backdrop click (the dialog's parent overlay — not the dialog itself).
    rerender(
      <MemoryRouter>
        <AlbumPreviewModal row={row} onClose={onClose} />
      </MemoryRouter>,
    )
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(dialog.parentElement as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(2)

    // Clicks inside the dialog must NOT close it.
    rerender(
      <MemoryRouter>
        <AlbumPreviewModal row={row} onClose={onClose} />
      </MemoryRouter>,
    )
    const dialog3 = await screen.findByRole('dialog')
    fireEvent.click(dialog3)
    expect(onClose).toHaveBeenCalledTimes(2)

    // The close button closes too.
    await user.click(screen.getByRole('button', { name: 'Close preview' }))
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it('shows a preview fetch error inline and retries without dismissing', async () => {
    const user = userEvent.setup()
    mocks.api.previewAlbum.mockRejectedValueOnce(
      new mocks.ApiError(502, 'Provider error: deezer hung up'),
    )
    renderModal()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Provider error: deezer hung up')
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument() // still open

    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    await user.click(within(alert).getByRole('button', { name: /Retry/ }))
    expect(await screen.findByText('Born Under Punches')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('disables the import button for read-only accounts', async () => {
    mocks.useAuth.mockReturnValue(defaultAuth({ canEdit: false }))
    mocks.api.previewAlbum.mockResolvedValue(mergedPreview)
    renderModal()
    await screen.findByRole('dialog')
    expect(
      screen.getByRole('button', { name: /Import this album/ }),
    ).toBeDisabled()
  })
})