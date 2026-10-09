import type {
  Album,
  AlbumImport,
  AlbumListParams,
  AlbumPreview,
  AlbumUpdate,
  LoginResult,
  ManualAlbumInput,
  Play,
  Recommendation,
  RecommendationParams,
  RegisterResult,
  Role,
  SearchResult,
  Tag,
  TrackSearchResult,
  User,
  UserAdmin,
  UserCreate,
} from './types'

const TOKEN_KEY = 'vynl_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`/api${path}`, { ...options, headers })

  if (res.status === 401) {
    clearToken()
    if (!path.startsWith('/auth/login')) window.location.assign('/login')
    throw new ApiError(401, 'Not authenticated')
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }

  if (!res.ok) {
    const detail =
      typeof (body as { detail?: unknown })?.detail === 'string'
        ? ((body as { detail: string }).detail)
        : res.statusText
    throw new ApiError(res.status, detail)
  }

  return body as T
}

export const api = {
  // ---- Auth ----
  register: (data: { name: string; email: string; password: string; invite_code: string }) =>
    request<RegisterResult>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  login: (data: { email: string; password: string }) =>
    request<LoginResult>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  me: () => request<User>('/auth/me'),

  // ---- Admin: user management (issue #9) ----
  listUsers: () => request<UserAdmin[]>('/users'),
  createUser: (data: UserCreate) =>
    request<UserAdmin>('/users', { method: 'POST', body: JSON.stringify(data) }),
  approveUser: (id: number) =>
    request<UserAdmin>(`/users/${id}/approve`, { method: 'POST' }),
  denyUser: (id: number) => request<UserAdmin>(`/users/${id}/deny`, { method: 'POST' }),
  setUserRole: (id: number, role: Role) =>
    request<UserAdmin>(`/users/${id}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    }),
  resetUserPassword: (id: number, password: string) =>
    request<UserAdmin>(`/users/${id}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: 'DELETE' }),

  // ---- External search (add-album flow) ----
  searchAlbums: (q: string, limit = 20) => {
    const qs = new URLSearchParams({ q, limit: String(limit) })
    return request<SearchResult[]>(`/search/albums?${qs.toString()}`)
  },

  // ---- Collection ----
  importAlbum: (data: AlbumImport) =>
    request<Album>('/albums/import', { method: 'POST', body: JSON.stringify(data) }),
  /** Manually create an album with a user-entered tracklist (issue #11). */
  createManualAlbum: (input: ManualAlbumInput) =>
    request<Album>('/albums/manual', { method: 'POST', body: JSON.stringify(input) }),
  /**
   * Upload a cover image (JPEG-normalized by the CoverPicker) via a multipart
   * `PUT /albums/{id}/cover` (FormData `file` field) with a Bearer token.
   * The declared content type is only a hint — the backend sniffs the bytes.
   * Surfaces the API's 400 detail.
   */
  uploadAlbumCover: async (id: number, blob: Blob): Promise<Album> => {
    // Multipart PUT /albums/{id}/cover (#11): FormData so the browser sets
    // the multipart boundary; the backend sniffs the bytes regardless.
    const form = new FormData()
    form.append('file', blob, 'cover.jpg')
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
    let res: Response
    try {
      res = await fetch(`/api/albums/${id}/cover`, {
        method: 'PUT',
        headers,
        body: form,
      })
    } catch {
      throw new ApiError(0, 'Network error')
    }
    if (res.status === 401) {
      clearToken()
      window.location.assign('/login')
      throw new ApiError(401, 'Not authenticated')
    }
    const text = await res.text()
    let body: unknown = null
    try {
      body = text ? JSON.parse(text) : null
    } catch {
      body = null
    }
    if (!res.ok) {
      const detail =
        typeof (body as { detail?: unknown })?.detail === 'string'
          ? ((body as { detail: string }).detail)
          : res.statusText
      throw new ApiError(res.status, detail)
    }
    return body as Album
  },
  /** Dry-run preview of import (issue #13): what the album would look like. */
  previewAlbum: (data: AlbumImport) =>
    request<AlbumPreview>('/albums/preview', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listAlbums: (params: AlbumListParams = {}) => {
    const qs = new URLSearchParams()
    if (params.q) qs.set('q', params.q)
    if (params.tag) qs.set('tag', params.tag)
    if (params.favorite !== undefined) qs.set('favorite', String(params.favorite))
    if (params.sort) qs.set('sort', params.sort)
    if (params.limit !== undefined) qs.set('limit', String(params.limit))
    if (params.offset !== undefined) qs.set('offset', String(params.offset))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request<Album[]>(`/albums${suffix}`)
  },
  getAlbum: (id: number) => request<Album>(`/albums/${id}`),
  updateAlbum: (id: number, data: AlbumUpdate) =>
    request<Album>(`/albums/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteAlbum: (id: number) => request<void>(`/albums/${id}`, { method: 'DELETE' }),
  /** Cover image URL for an album; falls back to `album.cover_url` on 404. */
  getCoverUrl: (id: number) => `/api/albums/${id}/cover`,

  /**
   * Fetch the cached cover image with auth (the cover endpoint is
   * `get_current_user`-gated, so a bare `<img>` can't load it). Returns
   * `null` on 404/error; callers should revoke any blob URL they create.
   */
  getCoverBlob: async (id: number): Promise<Blob | null> => {
    try {
      const token = getToken()
      const res = await fetch(`/api/albums/${id}/cover`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) return null
      return await res.blob()
    } catch {
      return null
    }
  },

  // ---- Tags ----
  getTags: () => request<Tag[]>('/tags'),
  createTag: (name: string) =>
    request<Tag>('/tags', { method: 'POST', body: JSON.stringify({ name }) }),
  setAlbumTags: (id: number, tags: string[]) =>
    request<Album>(`/albums/${id}/tags`, { method: 'PUT', body: JSON.stringify({ tags }) }),

  // ---- Plays ----
  logPlay: (id: number, playedAt?: string) =>
    request<Album>(`/albums/${id}/plays`, {
      method: 'POST',
      body: JSON.stringify(playedAt ? { played_at: playedAt } : {}),
    }),
  listPlays: (id: number) => request<Play[]>(`/albums/${id}/plays`),
  deletePlay: (id: number, playId: number) =>
    request<void>(`/albums/${id}/plays/${playId}`, { method: 'DELETE' }),

  // ---- Library song search ----
  searchTracks: (q: string, limit = 50) => {
    const qs = new URLSearchParams({ q, limit: String(limit) })
    return request<TrackSearchResult[]>(`/tracks?${qs.toString()}`)
  },

  // ---- Recommendations ----
  getRecommendations: (params: RecommendationParams = {}) => {
    const qs = new URLSearchParams()
    if (params.mode) qs.set('mode', params.mode)
    if (params.tag) qs.set('tag', params.tag)
    if (params.n !== undefined) qs.set('n', String(params.n))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request<Recommendation[]>(`/recommendations${suffix}`)
  },
}
