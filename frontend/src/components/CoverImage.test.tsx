import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CoverImage } from './CoverImage'

const mocks = vi.hoisted(() => ({
  api: {
    getCoverUrl: vi.fn(),
    getCoverBlob: vi.fn().mockResolvedValue(null),
  },
}))

vi.mock('../api', () => ({ api: mocks.api }))

mocks.api.getCoverUrl.mockImplementation((id: number) => `/api/albums/${id}/cover`)

beforeEach(() => {
  mocks.api.getCoverBlob.mockResolvedValue(null)
  URL.createObjectURL = vi.fn(() => 'blob:mock-cover') as typeof URL.createObjectURL
  URL.revokeObjectURL = vi.fn()
})

describe('CoverImage', () => {
  it('points at the cached cover endpoint first and lazy-loads', () => {
    render(<CoverImage albumId={5} coverUrl="https://example.com/x.jpg" alt="X cover" />)
    const img = screen.getByRole('img', { name: 'X cover' })
    expect(img).toHaveAttribute('src', '/api/albums/5/cover')
    expect(img).toHaveAttribute('loading', 'lazy')
  })

  it('falls back to the remote cover_url when the cached cover 404s', () => {
    render(<CoverImage albumId={5} coverUrl="https://example.com/x.jpg" alt="X cover" />)
    fireEvent.error(screen.getByRole('img', { name: 'X cover' }))
    expect(screen.getByRole('img', { name: 'X cover' })).toHaveAttribute(
      'src',
      'https://example.com/x.jpg',
    )
  })

  it('renders a placeholder after the fallback also fails', () => {
    render(<CoverImage albumId={5} coverUrl="https://example.com/x.jpg" alt="X cover" />)
    fireEvent.error(screen.getByRole('img', { name: 'X cover' }))
    fireEvent.error(screen.getByRole('img', { name: 'X cover' }))
    expect(screen.getByRole('img', { name: 'X cover' })).toHaveTextContent('No cover')
  })

  it('uses cover_url directly for un-imported search results', () => {
    render(<CoverImage albumId={null} coverUrl="https://example.com/d.jpg" alt="D cover" />)
    expect(screen.getByRole('img', { name: 'D cover' })).toHaveAttribute(
      'src',
      'https://example.com/d.jpg',
    )
  })

  it('renders a placeholder when there is no art at all', () => {
    render(<CoverImage albumId={5} coverUrl={null} alt="None cover" />)
    fireEvent.error(screen.getByRole('img', { name: 'None cover' }))
    expect(screen.getByRole('img', { name: 'None cover' })).toHaveTextContent('No cover')
  })

  it('uses the auth-fetched cached cover blob when it resolves', async () => {
    mocks.api.getCoverBlob.mockResolvedValue(new Blob(['image'], { type: 'image/jpeg' }))
    render(<CoverImage albumId={5} coverUrl="https://example.com/x.jpg" alt="X cover" />)
    const img = await screen.findByRole('img', { name: 'X cover' })
    // The cached blob URL replaces the raw endpoint src as soon as it arrives.
    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'blob:mock-cover'))
    expect(mocks.api.getCoverBlob).toHaveBeenCalledWith(5)
  })

  it('falls back when the cached cover blob is unavailable', async () => {
    render(<CoverImage albumId={5} coverUrl="https://example.com/x.jpg" alt="X cover" />)
    const img = await screen.findByRole('img', { name: 'X cover' })
    expect(img).toHaveAttribute('src', '/api/albums/5/cover')
    fireEvent.error(img)
    expect(screen.getByRole('img', { name: 'X cover' })).toHaveAttribute(
      'src',
      'https://example.com/x.jpg',
    )
  })
})