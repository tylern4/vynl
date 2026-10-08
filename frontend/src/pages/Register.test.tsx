import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RegisterPage } from './Register'
import { defaultAuth, testUser } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = { register: vi.fn() }
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

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <RegisterPage />
    </MemoryRouter>,
  )
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Name'), '  Tester  ')
  await user.type(screen.getByLabelText('Email'), 't@t.com')
  await user.type(screen.getByLabelText('Password'), 'secret1234')
  await user.type(screen.getByLabelText(/Setup code/), ' bumblebee ')
}

beforeEach(() => {
  mocks.useAuth.mockReset()
})

describe('RegisterPage', () => {
  it('submits trimmed registration details', async () => {
    const user = userEvent.setup()
    const register = vi.fn().mockResolvedValue({ user: testUser, access_token: 'tok' })
    mocks.useAuth.mockReturnValue(defaultAuth({ register }))
    renderRegister()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith('Tester', 't@t.com', 'secret1234', 'bumblebee'),
    )
  })

  it('shows a pending message when no token is returned', async () => {
    const user = userEvent.setup()
    const register = vi.fn().mockResolvedValue({ user: testUser, access_token: null })
    mocks.useAuth.mockReturnValue(defaultAuth({ register }))
    renderRegister()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText(/awaiting approval/)).toBeInTheDocument()
  })

  it('shows the API error message on failure', async () => {
    const user = userEvent.setup()
    const register = vi.fn().mockRejectedValue(new mocks.ApiError(400, 'Email already registered'))
    mocks.useAuth.mockReturnValue(defaultAuth({ register }))
    renderRegister()

    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByText('Email already registered')).toBeInTheDocument()
  })
})
