// Axios 客户端 + JWT 注入 + 401 自动刷新/登出。
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'vgp_access_token'
const REFRESH_KEY = 'vgp_refresh_token'
const ROLES_KEY = 'vgp_roles'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  getRoles: (): string[] => JSON.parse(localStorage.getItem(ROLES_KEY) || '[]'),
  set: (access: string, refresh: string, roles: string[]) => {
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
    localStorage.setItem(ROLES_KEY, JSON.stringify(roles))
  },
  setAccess: (access: string) => localStorage.setItem(TOKEN_KEY, access),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(ROLES_KEY)
  },
}

export const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.get()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing: Promise<string | null> | null = null

async function refreshAccess(): Promise<string | null> {
  const refresh = tokenStore.getRefresh()
  if (!refresh) return null
  try {
    const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refresh })
    tokenStore.setAccess(data.access_token)
    return data.access_token as string
  } catch {
    return null
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean }
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true
      refreshing = refreshing || refreshAccess()
      const newToken = await refreshing
      refreshing = null
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      }
      tokenStore.clear()
      if (location.pathname !== '/login') location.assign('/login')
    }
    return Promise.reject(error)
  },
)
