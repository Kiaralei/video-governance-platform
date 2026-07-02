import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore } from '../api/client'
import type { LoginResponse } from '../api/types'

interface AuthState {
  roles: string[]
  authed: boolean
  login: (username: string, password: string) => Promise<string[]>
  logout: () => void
  hasRole: (...roles: string[]) => boolean
}

const AuthCtx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [roles, setRoles] = useState<string[]>(tokenStore.getRoles())
  const [authed, setAuthed] = useState<boolean>(!!tokenStore.get())

  const value = useMemo<AuthState>(
    () => ({
      roles,
      authed,
      hasRole: (...want: string[]) => want.some((r) => roles.includes(r)),
      login: async (username, password) => {
        const { data } = await api.post<LoginResponse>('/auth/login', { username, password })
        tokenStore.set(data.access_token, data.refresh_token, data.roles)
        setRoles(data.roles)
        setAuthed(true)
        return data.roles
      },
      logout: () => {
        tokenStore.clear()
        setRoles([])
        setAuthed(false)
      },
    }),
    [roles, authed],
  )

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return ctx
}
