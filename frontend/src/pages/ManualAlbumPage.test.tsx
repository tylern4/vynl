import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import type { Album } from '../types'
import { ManualAlbumPage, parseDurationInput } from './ManualAlbumPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    createManualAlbum: vi.fn(),
    uploadAlbumCover: vi.fn(),
  }
  const normalizeCoverFile = vi.fn()
  const useAuth = vi.fn()
  class ApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return { api, normalizeCoverFile, useAuth, ApiError }
})

vi.mock('../api', () => ({ api: mocks.api, ApiError: mocks.ApiError }))
vi.mock('../components/coverNormalize', () => ({
  normalizeCoverFile: mocks.normalizeCoverFile,
}))
vi.mock('../auth', () => ({ useAuth: () => mocks.useAuth() }))

const created: Album = {
  id: 55,
  title: 'Demo Tape',
  artist: 'Local Band',
  year: 2021,
  label: null,
  country: null,
  source: 'manual',
  external_id: 'manual-abc',
  cover_url: null,
  track_count: 1,
  favorite: false,
  note: null,
  last_played_at: null,
  tags: [],
  created_at: '2026-01-01T00:00:00Z',
}

function NavigatedAlbum() {
  const { id } = useParams()
  return <div data-testid="navigated">Album {id}</div>
}

function renderManual() {
  return render(
    <MemoryRouter initialEntries={['/add/manual']}>
      <Routes>
        <Route path="/add/manual" element={<ManualAlbumPage />} />
        <Route path="/album/:id" element={<NavigatedAlbum />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** Attach a file to a file input the way jsdom requires. */
function uploadFile(input: HTMLElement, file: File) {
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

async function fillBasics(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Title *'), 'Demo Tape')
  await user.type(screen.getByLabelText('Artist *'), 'Local Band')
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  mocks.api.createManualAlbum.mockReset()
  mocks.api.uploadAlbumCover.mockReset()
  mocks.normalizeCoverFile.mockReset()
  mocks.useAuth.mockReturnValue(defaultAuth())
  URL.createObjectURL = vi.fn(() => 'blob:preview') as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn()
})

describe('parseDurationInput', () => {
  it('treats blank input as "not supplied"', () => {
    expect(parseDurationInput('')).toBeNull()
    expect(parseDurationInput('   ')).toBeNull()
  })

  it('accepts plain seconds', () => {
    expect(parseDurationInput('225')).toBe(225)
    expect(parseDurationInput('0')).toBe(0)
  })

  it('accepts m:ss notation', () => {
    expect(parseDurationInput('3:45')).toBe(225)
    expect(parseDurationInput('12:05')).toBe(725)
  })

  it('rejects malformed durations', () => {
    expect(parseDurationInput('3:4')).toBe('invalid')
    expect(parseDurationInput('3:60')).toBe('invalid')
    expect(parseDurationInput('1:2:3')).toBe('invalid')
    expect(parseDurationInput('abc')).toBe('invalid')
  })
})

describe('ManualAlbumPage', () => {
  it('requires a title and artist before submitting', async () => {
    const user = userEvent.setup()
    renderManual()

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    expect(await screen.findByText('Title is required')).toBeInTheDocument()
    expect(screen.getByText('Artist is required')).toBeInTheDocument()
    expect(mocks.api.createManualAlbum).not.toHaveBeenCalled()
  })

  it('creates a manual album and navigates to its detail page', async () => {
    const user = userEvent.setup()
    mocks.api.createManualAlbum.mockResolvedValue(created)
    renderManual()
    await fillBasics(user)

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    await waitFor(() =>
      expect(mocks.api.createManualAlbum).toHaveBeenCalledWith({
        title: 'Demo Tape',
        artist: 'Local Band',
        year: undefined,
        label: undefined,
        country: undefined,
        note: undefined,
        tracks: [],
      }),
    )
    expect(await screen.findByTestId('navigated')).toHaveTextContent('Album 55')
  })

  it('edits a dynamic tracklist, parsing m:ss and seconds durations', async () => {
    const user = userEvent.setup()
    mocks.api.createManualAlbum.mockResolvedValue(created)
    renderManual()
    await fillBasics(user)

    await user.click(screen.getByRole('button', { name: 'Add track' }))
    await user.click(screen.getByRole('button', { name: 'Add track' }))
    expect(screen.getAllByLabelText(/Track \d title/)).toHaveLength(2)

    await user.type(screen.getByLabelText('Track 1 title'), 'Song A')
    await user.type(screen.getByLabelText('Track 1 duration'), '3:45')
    await user.type(screen.getByLabelText('Track 2 title'), 'Song B')
    await user.type(screen.getByLabelText('Track 2 duration'), '225')

    await user.click(screen.getByRole('button', { name: 'Remove track 2' }))
    expect(screen.queryByLabelText('Track 2 title')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    await waitFor(() =>
      expect(mocks.api.createManualAlbum).toHaveBeenCalledWith({
        title: 'Demo Tape',
        artist: 'Local Band',
        year: undefined,
        label: undefined,
        country: undefined,
        note: undefined,
        tracks: [{ title: 'Song A', duration_seconds: 225 }],
      }),
    )
  })

  it('flags an invalid track duration', async () => {
    const user = userEvent.setup()
    renderManual()
    await fillBasics(user)
    await user.click(screen.getByRole('button', { name: 'Add track' }))
    await user.type(screen.getByLabelText('Track 1 title'), 'Song A')
    await user.type(screen.getByLabelText('Track 1 duration'), '3:60')

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    expect(
      await screen.findByText('Duration must be like 3:45 or 225'),
    ).toBeInTheDocument()
    expect(mocks.api.createManualAlbum).not.toHaveBeenCalled()
  })

  it('validates the year range', async () => {
    const user = userEvent.setup()
    renderManual()
    await fillBasics(user)
    await user.type(screen.getByLabelText('Year'), '999')

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    expect(
      await screen.findByText(/Year must be between 1000 and/),
    ).toBeInTheDocument()
    expect(mocks.api.createManualAlbum).not.toHaveBeenCalled()
  })

  it('uploads the picked cover after creating the album, then navigates', async () => {
    const user = userEvent.setup()
    mocks.api.createManualAlbum.mockResolvedValue(created)
    mocks.api.uploadAlbumCover.mockResolvedValue(created)
    mocks.normalizeCoverFile.mockResolvedValue(
      new Blob(['jpeg'], { type: 'image/jpeg' }),
    )
    renderManual()
    await fillBasics(user)

    uploadFile(
      screen.getByLabelText('Upload cover image'),
      new File(['jpeg-bytes'], 'cover.jpg', { type: 'image/jpeg' }),
    )
    expect(await screen.findByAltText('Cover preview')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    await waitFor(() =>
      expect(mocks.api.uploadAlbumCover).toHaveBeenCalledWith(
        55,
        expect.any(Blob),
      ),
    )
    expect(await screen.findByTestId('navigated')).toHaveTextContent('Album 55')
  })

  it('keeps the album when the cover upload fails and offers a retry', async () => {
    const user = userEvent.setup()
    mocks.api.createManualAlbum.mockResolvedValue(created)
    mocks.api.uploadAlbumCover.mockRejectedValue(
      new mocks.ApiError(400, 'Not a valid image'),
    )
    mocks.normalizeCoverFile.mockResolvedValue(
      new Blob(['jpeg'], { type: 'image/jpeg' }),
    )
    renderManual()
    await fillBasics(user)
    uploadFile(
      screen.getByLabelText('Upload cover image'),
      new File(['jpeg-bytes'], 'cover.jpg', { type: 'image/jpeg' }),
    )
    await screen.findByAltText('Cover preview')

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    expect(
      await screen.findByText(/The album was added, but the cover upload failed/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Not a valid image/)).toBeInTheDocument()

    mocks.api.uploadAlbumCover.mockResolvedValue(created)
    await user.click(screen.getByRole('button', { name: 'Retry upload' }))
    await waitFor(() =>
      expect(mocks.api.uploadAlbumCover).toHaveBeenCalledTimes(2),
    )
    expect(await screen.findByTestId('navigated')).toHaveTextContent('Album 55')
  })

  it('links to an existing album on a 409 conflict', async () => {
    const user = userEvent.setup()
    mocks.api.createManualAlbum.mockRejectedValue(
      new mocks.ApiError(409, 'Album already in your shelf (id=42)'),
    )
    renderManual()
    await fillBasics(user)

    await user.click(screen.getByRole('button', { name: 'Add to shelf' }))
    const link = await screen.findByRole('link', { name: 'View album' })
    expect(link).toHaveAttribute('href', '/album/42')
  })

  it('links back to the search page', () => {
    renderManual()
    expect(screen.getByRole('link', { name: 'Back to search' })).toHaveAttribute(
      'href',
      '/add',
    )
  })
})