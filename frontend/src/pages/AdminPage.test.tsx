import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserAdmin } from '../types'
import { AdminPage } from './AdminPage'
import { defaultAuth } from '../test/utils'

const mocks = vi.hoisted(() => {
  const api = {
    listUsers: vi.fn(),
    createUser: vi.fn(),
    approveUser: vi.fn(),
    denyUser: vi.fn(),
    setUserRole: vi.fn(),
    resetUserPassword: vi.fn(),
    deleteUser: vi.fn(),
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

const adminUser: UserAdmin = {
  id: 1,
  name: 'Admin',
  email: 'admin@example.com',
  role: 'admin',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
}

const pendingUser: UserAdmin = {
  id: 2,
  name: 'Bob',
  email: 'bob@example.com',
  role: 'user',
  status: 'pending',
  created_at: '2026-02-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.useAuth.mockReturnValue(
    defaultAuth({
      user: { id: 1, name: 'Admin', email: 'admin@example.com', role: 'admin', status: 'active' },
    }),
  )
  mocks.api.listUsers.mockResolvedValue([adminUser, pendingUser])
})

function renderAdmin() {
  return render(<AdminPage />)
}

function rowFor(email: string): HTMLElement {
  return screen.getByText(email).closest('tr') as HTMLElement
}

describe('AdminPage', () => {
  it('lists users with their role and status', async () => {
    renderAdmin()
    expect(await screen.findByText('bob@example.com')).toBeInTheDocument()
    expect(screen.getByText('admin@example.com')).toBeInTheDocument()
    expect(within(rowFor('bob@example.com')).getByText('Pending')).toBeInTheDocument()
    expect(within(rowFor('admin@example.com')).getByText('Active')).toBeInTheDocument()
  })

  it('creates a user and confirms it in the list', async () => {
    const user = userEvent.setup()
    mocks.api.createUser.mockResolvedValue({
      id: 3,
      name: 'Carol',
      email: 'carol@example.com',
      role: 'user',
      status: 'active',
      created_at: '2026-03-01T00:00:00Z',
    })
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.type(screen.getByLabelText('Name'), 'Carol')
    await user.type(screen.getByLabelText('Email'), 'carol@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /add user/i }))

    await waitFor(() =>
      expect(mocks.api.createUser).toHaveBeenCalledWith({
        name: 'Carol',
        email: 'carol@example.com',
        password: 'password123',
        role: 'user',
      }),
    )
    expect(await screen.findByText('carol@example.com')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Carol added.')
  })

  it('surfaces a create error from the API', async () => {
    const user = userEvent.setup()
    mocks.api.createUser.mockRejectedValue(
      new mocks.ApiError(409, 'An account with that email already exists'),
    )
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.type(screen.getByLabelText('Name'), 'Dup')
    await user.type(screen.getByLabelText('Email'), 'bob@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: /add user/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'An account with that email already exists',
    )
  })

  it('approves a pending user', async () => {
    const user = userEvent.setup()
    mocks.api.approveUser.mockResolvedValue({ ...pendingUser, status: 'active' })
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(mocks.api.approveUser).toHaveBeenCalledWith(2))
    expect(await within(rowFor('bob@example.com')).findByText('Active')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
  })

  it('changes a user role', async () => {
    const user = userEvent.setup()
    mocks.api.setUserRole.mockResolvedValue({ ...pendingUser, role: 'read_only' })
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.selectOptions(screen.getByLabelText('Role for Bob'), 'read_only')

    await waitFor(() => expect(mocks.api.setUserRole).toHaveBeenCalledWith(2, 'read_only'))
  })

  it('resets a password through the inline control', async () => {
    const user = userEvent.setup()
    mocks.api.resetUserPassword.mockResolvedValue(pendingUser)
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.click(
      within(rowFor('bob@example.com')).getByRole('button', { name: 'Reset password' }),
    )
    await user.type(screen.getByLabelText('New password for Bob'), 'newpass123')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(mocks.api.resetUserPassword).toHaveBeenCalledWith(2, 'newpass123'),
    )
  })

  it('deletes only after an explicit confirmation', async () => {
    const user = userEvent.setup()
    mocks.api.deleteUser.mockResolvedValue(undefined)
    renderAdmin()
    await screen.findByText('bob@example.com')

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(mocks.api.deleteUser).not.toHaveBeenCalled()

    const confirmRow = screen.getByText(/undone/).closest('.confirm-row') as HTMLElement
    await user.click(within(confirmRow).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(mocks.api.deleteUser).toHaveBeenCalledWith(2))
    await waitFor(() => expect(screen.queryByText('bob@example.com')).toBeNull())
  })

  it("protects the current admin's own row", async () => {
    renderAdmin()
    await screen.findByText('admin@example.com')
    const row = rowFor('admin@example.com')

    expect(within(row).getByText('You')).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Delete' })).toBeNull()
    expect(within(row).queryByRole('button', { name: 'Deny' })).toBeNull()
    expect(within(row).getByLabelText('Role for Admin')).toBeDisabled()
  })

  it('shows an error when the user list fails to load', async () => {
    mocks.api.listUsers.mockRejectedValue(new mocks.ApiError(500, 'Boom'))
    renderAdmin()
    expect(await screen.findByRole('alert')).toHaveTextContent('Boom')
  })
})
