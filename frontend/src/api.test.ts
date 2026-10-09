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

describe('createManualAlbum', () => {
  it('posts the manual payload to /albums/manual', async () => {
    mockFetch(201, { id: 9 })
    await api.createManualAlbum({
      title: 'Demo Tape',
      artist: 'Local Band',
      year: 2021,
      tracks: [{ title: 'Song A', duration_seconds: 225 }],
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums/manual',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          title: 'Demo Tape',
          artist: 'Local Band',
          year: 2021,
          tracks: [{ title: 'Song A', duration_seconds: 225 }],
        }),
      }),
    )
  })
})

describe('uploadAlbumCover', () => {
  it('multipart-PUTs the file with a bearer token and returns the album', async () => {
    setToken('tok123')
    mockFetch(200, { id: 7 })
    const blob = new Blob(['jpeg'], { type: 'image/jpeg' })

    await expect(api.uploadAlbumCover(7, blob)).resolves.toEqual({ id: 7 })
    expect(fetch).toHaveBeenCalledWith(
      '/api/albums/7/cover',
      expect.objectContaining({
        method: 'PUT',
        headers: expect.objectContaining({ Authorization: 'Bearer tok123' }),
        body: expect.any(FormData),
      }),
    )
    const [, init] = vi.mocked(fetch).mock.calls[0] as [
      string,
      RequestInit | undefined,
    ]
    const form = init?.body as FormData
    const file = form.get('file') as File
    expect(file).toBeInstanceOf(Blob) // the `file` field carries the cover
    expect(file.size).toBe(blob.size) // (append() wraps the blob as a File)
  })

  it('surfaces the API 400 detail for an invalid image', async () => {
    mockFetch(400, { detail: 'Not a valid image' })
    await expect(
      api.uploadAlbumCover(7, new Blob(['x'])),
    ).rejects.toThrow('Not a valid image')
  })

  it('throws an ApiError with status 0 on network failure', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('NetworkError'))
    const error = await api
      .uploadAlbumCover(7, new Blob(['x']))
      .then(() => null)
      .catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(0)
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

describe('admin user management', () => {
  it('lists users', async () => {
    mockFetch(200, [{ id: 1, email: 'a@example.com' }])
    await expect(api.listUsers()).resolves.toEqual([{ id: 1, email: 'a@example.com' }])
    expect(fetch).toHaveBeenCalledWith('/api/users', expect.objectContaining({ headers: {} }))
  })

  it('posts the new user payload to /users', async () => {
    setToken('tok123')
    mockFetch(201, { id: 3, email: 'carol@example.com' })
    await api.createUser({
      name: 'Carol',
      email: 'carol@example.com',
      password: 'password123',
      role: 'user',
    })
    expect(fetch).toHaveBeenCalledWith('/api/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer tok123',
      },
      body: JSON.stringify({
        name: 'Carol',
        email: 'carol@example.com',
        password: 'password123',
        role: 'user',
      }),
    })
  })

  it('posts to the action routes for approve, deny, and reset-password', async () => {
    setToken('tok123')
    mockFetch(200, { id: 2 })
    await api.approveUser(2)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/users/2/approve',
      expect.objectContaining({ method: 'POST' }),
    )
    mockFetch(200, { id: 2 })
    await api.denyUser(2)
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/users/2/deny',
      expect.objectContaining({ method: 'POST' }),
    )
    mockFetch(200, { id: 2 })
    await api.resetUserPassword(2, 'newpass123')
    expect(fetch).toHaveBeenLastCalledWith('/api/users/2/reset-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer tok123',
      },
      body: JSON.stringify({ password: 'newpass123' }),
    })
  })

  it('patch-changes a role and deletes a user', async () => {
    setToken('tok123')
    mockFetch(200, { id: 2, role: 'read_only' })
    await api.setUserRole(2, 'read_only')
    expect(fetch).toHaveBeenLastCalledWith('/api/users/2/role', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer tok123',
      },
      body: JSON.stringify({ role: 'read_only' }),
    })

    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api.deleteUser(2)).resolves.toBeUndefined()
    expect(fetch).toHaveBeenLastCalledWith(
      '/api/users/2',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
