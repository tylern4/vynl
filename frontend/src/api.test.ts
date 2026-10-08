import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, clearToken, getToken, setToken } from './api'

const assignMock = vi.fn()

Object.defineProperty(window, 'location', {
  writable: true,
  value: { ...window.location, assign: assignMock },
})

function mockFetch(status: number, body: unknown) {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

beforeEach(() => {
  localStorage.clear()
  assignMock.mockClear()
  vi.stubGlobal('fetch', vi.fn())
})

describe('token storage', () => {
  it('round-trips the token under the vynl_token key', () => {
    expect(getToken()).toBeNull()
    setToken('abc')
    expect(localStorage.getItem('vynl_token')).toBe('abc')
    expect(getToken()).toBe('abc')
    clearToken()
    expect(getToken()).toBeNull()
  })
})

describe('request', () => {
  it('sends the auth header when a token is stored', async () => {
    setToken('tok123')
    mockFetch(200, [])
    await api.listAlbums()
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer tok123' }),
      }),
    )
  })

  it('sends a JSON content-type when a body is present', async () => {
    mockFetch(200, { access_token: 'x', token_type: 'bearer', user: {} })
    await api.login({ email: 'a@b.com', password: 'secret1' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('returns parsed JSON on success', async () => {
    mockFetch(200, { status: 'ok' })
    await expect(api.me()).resolves.toEqual({ status: 'ok' })
  })

  it('builds query strings for list endpoints', async () => {
    mockFetch(200, [])
    await api.searchAlbums('remain in light', 5)
    expect(fetch).toHaveBeenCalledWith('/api/search/albums?q=remain+in+light&limit=5', expect.anything())
    mockFetch(200, [])
    await api.getRecommendations({ mode: 'dusty', tag: 'summer', n: 3 })
    expect(fetch).toHaveBeenCalledWith(
      '/api/recommendations?mode=dusty&tag=summer&n=3',
      expect.anything(),
    )
  })

  it('returns undefined for 204 responses', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.deleteAlbum(3)).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums/3',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('surfaces the API detail message on errors', async () => {
    mockFetch(409, { detail: 'Already on your shelf (album 12)' })
    await expect(
      api.importAlbum({ source: 'deezer', external_id: '302127' }),
    ).rejects.toThrow('Already on your shelf (album 12)')
  })

  it('posts the payload to /albums/preview for previewAlbum', async () => {
    mockFetch(200, { title: 'Remain in Light', tracks: [] })
    await api.previewAlbum({ source: 'deezer', external_id: '302127' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums/preview',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ source: 'deezer', external_id: '302127' }),
      }),
    )
  })

  it('throws ApiError with the status code', async () => {
    mockFetch(500, { detail: 'boom' })
    const error = await api
      .listAlbums()
      .then(() => null)
      .catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(500)
  })

  it('clears the token and redirects to login on 401', async () => {
    setToken('expired')
    mockFetch(401, { detail: 'Not authenticated' })
    await expect(api.listAlbums()).rejects.toMatchObject({ status: 401 })
    expect(getToken()).toBeNull()
    expect(assignMock).toHaveBeenCalledWith('/login')
  })

  it('does not redirect for a failed login', async () => {
    mockFetch(401, { detail: 'Incorrect email or password' })
    await expect(
      api.login({ email: 'a@b.com', password: 'wrong' }),
    ).rejects.toMatchObject({ status: 401 })
    expect(assignMock).not.toHaveBeenCalled()
  })
})

describe('getCoverUrl', () => {
  it('points at the cached cover endpoint', () => {
    expect(api.getCoverUrl(7)).toBe('/api/albums/7/cover')
  })
})

describe('getCoverBlob', () => {
  it('fetches the cached cover with the bearer token and returns a blob', async () => {
    setToken('tok123')
    const blob = new Blob(['jpeg-bytes'], { type: 'image/jpeg' })
    vi.mocked(fetch).mockResolvedValue(new Response(blob, { status: 200 }))

    const result = await api.getCoverBlob(7)
    expect(result).not.toBeNull()
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums/7/cover',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer tok123' }),
      }),
    )
  })

  it('returns null when the cover is missing', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 404 }))
    await expect(api.getCoverBlob(7)).resolves.toBeNull()
  })

  it('returns null on network failure', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('NetworkError'))
    await expect(api.getCoverBlob(7)).resolves.toBeNull()
  })
})
