import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { LoginPage } from './Login'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = { login: vi.fn() }
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
vi.mock('../auth', () => ({
  AuthProvider: ({ children }: { children: import('react').ReactNode }) => children,
  useAuth: () => mocks.useAuth(),
  ProtectedRoute: ({ children }: { children: import('react').ReactNode }) => children,
}))

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <LoginPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mocks.useAuth.mockReset()
})

describe('LoginPage', () => {
  it('submits credentials to login', async () => {
    const user = userEvent.setup()
    const login = vi.fn().mockResolvedValue(undefined)
    mocks.useAuth.mockReturnValue(defaultAuth({ login }))
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 't@t.com')
    await user.type(screen.getByLabelText('Password'), 'secret1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('t@t.com', 'secret1'))
  })

  it('shows the API error message on failure', async () => {
    const user = userEvent.setup()
    const login = vi.fn().mockRejectedValue(new mocks.ApiError(401, 'Incorrect email or password'))
    mocks.useAuth.mockReturnValue(defaultAuth({ login }))
    renderLogin()

    await user.type(screen.getByLabelText('Email'), 't@t.com')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Incorrect email or password')).toBeInTheDocument()
  })
})
