import { vi } from 'vitest'
import type { Mock } from 'vitest'
import type { User } from '../types'

export const testUser: User = {
  id: 1,
  name: 'Tester',
  email: 'tester@example.com',
  role: 'admin',
  status: 'active',
}

export interface TestAuthState {
  user: User | null
  loading: boolean
  canEdit: boolean
  login: Mock
  register: Mock
  setToken: Mock
  logout: Mock
}

export function defaultAuth(overrides: Partial<TestAuthState> = {}): TestAuthState {
  return {
    user: testUser,
    loading: false,
    canEdit: true,
    login: vi.fn(),
    register: vi.fn(),
    setToken: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  }
}
