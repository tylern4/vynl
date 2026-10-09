import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AdminRoute, AuthProvider } from './auth'
import type { Role } from './types'

const mocks = vi.hoisted(() => ({
  getToken: vi.fn(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  me: vi.fn(),
}))

vi.mock('./api', () => ({
  api: { me: mocks.me },
  getToken: mocks.getToken,
  setToken: mocks.setToken,
  clearToken: mocks.clearToken,
}))

function renderAt(role: Role) {
  mocks.getToken.mockReturnValue('tok')
  mocks.me.mockResolvedValue({
    id: 1,
    name: 'Tester',
    email: 'tester@example.com',
    role,
    status: 'active',
  })
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/" element={<div>shelf home</div>} />
          <Route path="/login" element={<div>login page</div>} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div>admin panel</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

describe('AdminRoute', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the page for admins', async () => {
    renderAt('admin')
    expect(await screen.findByText('admin panel')).toBeInTheDocument()
  })

  it('redirects a regular user to the shelf', async () => {
    renderAt('user')
    expect(await screen.findByText('shelf home')).toBeInTheDocument()
    expect(screen.queryByText('admin panel')).toBeNull()
  })

  it('redirects a read-only user to the shelf', async () => {
    renderAt('read_only')
    expect(await screen.findByText('shelf home')).toBeInTheDocument()
  })

  it('sends anonymous visitors to the login page', async () => {
    mocks.getToken.mockReturnValue(null)
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/admin']}>
          <Routes>
            <Route path="/login" element={<div>login page</div>} />
            <Route
              path="/admin"
              element={
                <AdminRoute>
                  <div>admin panel</div>
                </AdminRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )
    expect(await screen.findByText('login page')).toBeInTheDocument()
  })
})
