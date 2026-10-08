import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from './auth'
import App from './App'
import { testUser } from './test/utils'

function renderApp(initial = '/') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function userResponse() {
  return new Response(JSON.stringify(testUser), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn())
})

describe('App routing', () => {
  it('renders the login page when logged out', async () => {
    renderApp('/')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByText('vynl')).toBeInTheDocument()
  })

  it('redirects protected routes to the login page', async () => {
    renderApp('/add')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows loading while authentication is in progress', () => {
    localStorage.setItem('vynl_token', 'tok')
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    renderApp('/')
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('renders the shelf for an authenticated user', async () => {
    localStorage.setItem('vynl_token', 'tok')
    vi.mocked(fetch).mockResolvedValue(userResponse())
    renderApp('/')
    expect(await screen.findByRole('heading', { name: 'The shelf' })).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/auth/me', expect.anything())
    expect(screen.getByRole('navigation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Toggle theme' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings',
    )
    expect(screen.getByRole('button', { name: 'Log out' })).toBeInTheDocument()
  })
})
