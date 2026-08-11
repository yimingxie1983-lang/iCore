

import { create } from 'zustand'

import { queryClient } from '@/shared/foundation/queryClient'

const TOKEN_KEY = 'cc_access_token'
const USER_KEY = 'cc_user'

export interface AuthUser {
  id: string
  username: string
  email: string
  display_name: string
  role: 'admin' | 'user' | string
  status: string

  permissions?: string[]

  roles?: { id: string; name: string }[]
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

function readStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  } catch {
    return null
  }
}

interface AuthState {
  token: string | null
  user: AuthUser | null

  isAdmin: boolean
  setAuth: (token: string, user: AuthUser) => void
  setUser: (user: AuthUser) => void
  logout: () => void
}

export function checkPermission(user: AuthUser | null, perm: string): boolean {
  if (!user) return false
  if (user.role === 'admin') return true
  return (user.permissions || []).includes(perm)
}

export const useAuthStore = create<AuthState>((set) => ({
  token: getToken(),
  user: readStoredUser(),
  isAdmin: readStoredUser()?.role === 'admin',

  setAuth: (token, user) => {
    try {
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    } catch {

    }

    queryClient.clear()
    set({ token, user, isAdmin: user.role === 'admin' })
  },

  setUser: (user) => {
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    } catch {

    }
    set({ user, isAdmin: user.role === 'admin' })
  },

  logout: () => {
    try {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    } catch {

    }

    queryClient.clear()
    set({ token: null, user: null, isAdmin: false })
  },
}))

export function forceLogout(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {

  }

  try {
    useAuthStore.setState({ token: null, user: null, isAdmin: false })
    queryClient.clear()
  } catch {

  }
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login')
  }
}

export function useHasPermission(perm: string): boolean {
  return useAuthStore((s) => checkPermission(s.user, perm))
}
