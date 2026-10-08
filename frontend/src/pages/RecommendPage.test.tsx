import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { Album, Recommendation, Tag } from '../types'
import { RecommendPage } from './RecommendPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    getRecommendations: vi.fn(),
    getTags: vi.fn(),
    logPlay: vi.fn(),
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

const recs: Recommendation[] = [
  {
    album: { ...baseAlbum, id: 1, title: 'Remain in Light' },
    reason: "Haven't spun this since Aug 2026",
    days_since_played: 68,
  },
  {
    album: { ...baseAlbum, id: 2, title: 'Speaking in Tongues', favorite: false },
    reason: 'Never played',
    days_since_played: null,
  },
  {
    album: { ...baseAlbum, id: 3, title: 'Fear of Music', favorite: false },
    reason: 'Random pick',
    days_since_played: 12,
  },
]

const tags: Tag[] = [
  { id: 1, name: 'chill', album_count: 2 },
  { id: 2, name: 'summer', album_count: 1 },
]

function renderRec() {
  return render(
    <MemoryRouter>
      <RecommendPage />
    </MemoryRouter>,
  )
}

/** The article wrapping the title, so per-card buttons can be scoped. */
function findCard(title: string) {
  return screen.getByText(title).closest('article') as HTMLElement
}

beforeEach(() => {
  mocks.useAuth.mockReset()
  mocks.api.getRecommendations.mockReset()
  mocks.api.getTags.mockReset()
  mocks.api.logPlay.mockReset()
  mocks.api.getCoverBlob.mockResolvedValue(null)
  mocks.api.getRecommendations.mockResolvedValue(recs)
  mocks.api.getTags.mockResolvedValue(tags)
  mocks.useAuth.mockReturnValue(defaultAuth())
})

describe('RecommendPage', () => {
  it('spins on load and renders cards with reasons and days badges', async () => {
    renderRec()
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()
    expect(screen.getByText('Speaking in Tongues')).toBeInTheDocument()
    expect(screen.getByText('Fear of Music')).toBeInTheDocument()
    expect(screen.getByText("Haven't spun this since Aug 2026")).toBeInTheDocument()
    expect(screen.getByText('Never played')).toBeInTheDocument()
    expect(screen.getByText('Random pick')).toBeInTheDocument()
    expect(screen.getByText('68 days since spun')).toBeInTheDocument()
    expect(screen.getByText('12 days since spun')).toBeInTheDocument()
    await waitFor(() =>
      expect(mocks.api.getRecommendations).toHaveBeenCalledWith(
        expect.objectContaining({ mode: 'dusty', n: 3 }),
      ),
    )
  })

  it('links cards through to the album detail page', async () => {
    renderRec()
    const titleLink = await screen.findByRole('link', { name: 'Remain in Light' })
    expect(titleLink).toHaveAttribute('href', '/album/1')
    const coverLink = screen.getByRole('link', { name: 'Remain in Light cover' })
    expect(coverLink).toHaveAttribute('href', '/album/1')
  })

  it('switches to Random and spins with mode=random', async () => {
    const user = userEvent.setup()
    renderRec()
    await screen.findByText('Remain in Light')

    await user.click(screen.getByRole('button', { name: 'Random' }))
    expect(
      screen.getByText('A pure-chance pick from your whole shelf.'),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Spin' }))
    await waitFor(() =>
      expect(mocks.api.getRecommendations).toHaveBeenLastCalledWith(
        expect.objectContaining({ mode: 'random', n: 3 }),
      ),
    )
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()
  })

  it('includes the selected tag in the spin query', async () => {
    const user = userEvent.setup()
    renderRec()
    await screen.findByText('Remain in Light')

    await user.click(screen.getByRole('button', { name: /chill/ }))
    await user.click(screen.getByRole('button', { name: 'Spin' }))
    await waitFor(() =>
      expect(mocks.api.getRecommendations).toHaveBeenLastCalledWith(
        expect.objectContaining({ tag: 'chill', n: 3 }),
      ),
    )
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()
  })

  it('"Spun it" logs the play and shows the logged state', async () => {
    const user = userEvent.setup()
    mocks.api.logPlay.mockResolvedValue({
      ...baseAlbum,
      last_played_at: '2026-10-08T12:00:00Z',
    })
    renderRec()
    await screen.findByText('Remain in Light')

    const card = findCard('Remain in Light')
    await user.click(within(card).getByRole('button', { name: 'Spun it' }))
    await waitFor(() => expect(mocks.api.logPlay).toHaveBeenCalledWith(1))
    expect(await screen.findByText('Logged')).toBeInTheDocument()
    // The freshly-spun card no longer advertises its old “days since spun”.
    expect(screen.queryByText('68 days since spun')).not.toBeInTheDocument()
  })

  it('"Show me another" re-rolls just that slot with n=1', async () => {
    const user = userEvent.setup()
    const alternate: Recommendation = {
      album: {
        ...baseAlbum,
        id: 9,
        title: 'More Songs About Buildings and Food',
        favorite: false,
      },
      reason: 'Random pick',
      days_since_played: 4,
    }
    mocks.api.getRecommendations
      .mockResolvedValueOnce(recs)
      .mockResolvedValue([alternate])
    renderRec()
    await screen.findByText('Remain in Light')

    const card = findCard('Remain in Light')
    await user.click(within(card).getByRole('button', { name: 'Show me another' }))
    await waitFor(() =>
      expect(mocks.api.getRecommendations).toHaveBeenLastCalledWith(
        expect.objectContaining({ mode: 'dusty', n: 1 }),
      ),
    )
    expect(await screen.findByText('More Songs About Buildings and Food')).toBeInTheDocument()
    expect(screen.queryByText('Remain in Light')).not.toBeInTheDocument()
  })

  it('shows the empty-library CTA pointing at /add', async () => {
    mocks.api.getRecommendations.mockResolvedValue([])
    renderRec()
    expect(
      await screen.findByRole('heading', {
        name: 'Shelf is empty — add records to get picks',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add a record' })).toHaveAttribute(
      'href',
      '/add',
    )
  })

  it('offers to clear the tag when the filtered spin comes back empty', async () => {
    const user = userEvent.setup()
    mocks.api.getRecommendations.mockResolvedValue([])
    renderRec()
    await screen.findByRole('heading', {
      name: 'Shelf is empty — add records to get picks',
    })

    await user.click(screen.getByRole('button', { name: /chill/ }))
    await user.click(screen.getByRole('button', { name: 'Spin' }))
    expect(await screen.findByText('No records tagged “chill”')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Clear tag' }))
    expect(screen.getByRole('button', { name: /Any mood/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('shows a skeleton and a disabled spinner button while loading', () => {
    mocks.api.getRecommendations.mockReturnValue(new Promise(() => {}))
    renderRec()
    expect(screen.getAllByTestId('rec-skeleton')).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Spinning…' })).toBeDisabled()
  })

  it('shows an error state whose retry re-spins', async () => {
    const user = userEvent.setup()
    mocks.api.getRecommendations
      .mockRejectedValueOnce(new mocks.ApiError(502, 'Bad gateway'))
      .mockResolvedValue(recs)
    renderRec()
    expect(await screen.findByRole('alert')).toHaveTextContent('Bad gateway')

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Remain in Light')).toBeInTheDocument()
  })

  it('explains when a reroll must repeat a record on a tiny shelf', async () => {
    const user = userEvent.setup()
    // Initial spin delivers the slate; every reroll keeps returning card 1, so
    // the duplicate-guard gives up and accepts it.
    mocks.api.getRecommendations
      .mockResolvedValueOnce(recs)
      .mockResolvedValue([recs[0]])
    renderRec()
    await screen.findByText('Remain in Light')

    const card = findCard('Remain in Light')
    await user.click(within(card).getByRole('button', { name: 'Show me another' }))
    expect(await screen.findByText(/Tiny shelf/)).toBeInTheDocument()
    // The note explains why the record repeated instead of moving on.
    expect(screen.getByText(/rerolls fall back to repeats/)).toBeInTheDocument()
  })

  it('disables "Spun it" for read-only accounts', async () => {
    mocks.useAuth.mockReturnValue(defaultAuth({ canEdit: false }))
    renderRec()
    await screen.findByText('Remain in Light')

    const card = findCard('Remain in Light')
    expect(within(card).getByRole('button', { name: 'Spun it' })).toBeDisabled()
    expect(
      within(card).getByRole('button', { name: 'Show me another' }),
    ).not.toBeDisabled()
  })
})