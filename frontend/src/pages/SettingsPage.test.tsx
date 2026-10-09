import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { PALETTES, PALETTE_STORAGE_KEY } from '../theme'
import { defaultAuth } from '../test/utils'
import { SettingsPage } from './SettingsPage'

const mocks = vi.hoisted(() => ({ useAuth: vi.fn() }))

vi.mock('../auth', () => ({ useAuth: () => mocks.useAuth() }))

beforeEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.theme
  delete document.documentElement.dataset.palette
  mocks.useAuth.mockReturnValue(defaultAuth())
})

function renderSettings() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  )
}

function paletteButton(label: string) {
  return screen.getByRole('button', { name: new RegExp(`^${label} palette`) })
}

describe('SettingsPage', () => {
  it('renders a card for every palette', () => {
    renderSettings()
    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    for (const p of PALETTES) {
      expect(paletteButton(p.label)).toBeInTheDocument()
    }
  })

  it('marks the current palette as current', () => {
    renderSettings()
    expect(paletteButton('Default')).toHaveAttribute('aria-pressed', 'true')
    expect(
      within(paletteButton('Default')).getByText('Current'),
    ).toBeInTheDocument()
    expect(paletteButton('Cyberpunk')).toHaveAttribute('aria-pressed', 'false')
  })

  it('applies and persists a palette on click', async () => {
    const user = userEvent.setup()
    renderSettings()
    expect(document.documentElement.dataset.palette).toBe('default')

    await user.click(paletteButton('Cyberpunk'))

    expect(paletteButton('Cyberpunk')).toHaveAttribute('aria-pressed', 'true')
    expect(
      within(paletteButton('Cyberpunk')).getByText('Current'),
    ).toBeInTheDocument()
    expect(paletteButton('Default')).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.dataset.palette).toBe('cyberpunk')
    expect(localStorage.getItem(PALETTE_STORAGE_KEY)).toBe('cyberpunk')
  })

  it('switches the light/dark mode and persists it', async () => {
    const user = userEvent.setup()
    renderSettings()

    const group = screen.getByRole('group', { name: 'Color mode' })
    expect(within(group).getByRole('button', { name: 'Light' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    await user.click(within(group).getByRole('button', { name: 'Dark' }))

    expect(within(group).getByRole('button', { name: 'Dark' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('vynl_theme')).toBe('dark')
  })

  it('exposes accessible labels for the palette grid and its current state', () => {
    renderSettings()
    expect(
      screen.getByRole('group', { name: 'Choose a palette' }),
    ).toBeInTheDocument()
    expect(paletteButton('Death metal')).toHaveAccessibleName(
      'Death metal palette',
    )
  })

  it('shows admins a link to user management', () => {
    renderSettings()
    expect(screen.getByRole('link', { name: /manage users/i })).toHaveAttribute(
      'href',
      '/admin',
    )
  })

  it('hides the admin link from non-admins', () => {
    mocks.useAuth.mockReturnValue(
      defaultAuth({
        user: {
          id: 2,
          name: 'Bob',
          email: 'bob@example.com',
          role: 'user',
          status: 'active',
        },
      }),
    )
    renderSettings()
    expect(screen.queryByRole('link', { name: /manage users/i })).toBeNull()
  })
})