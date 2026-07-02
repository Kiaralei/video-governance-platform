export type AppRouteKey = '/workbench' | '/monitor' | '/policy' | '/appeals' | '/quality'

export const ROLES = {
  reviewer: 'reviewer',
  policyAdmin: 'policy_admin',
  systemAdmin: 'system_admin',
} as const

export const ROLE_LABELS: Record<string, string> = {
  [ROLES.reviewer]: '审核员',
  [ROLES.policyAdmin]: '策略管理员',
  [ROLES.systemAdmin]: '系统管理员',
}

export const ROUTE_ACCESS: Record<AppRouteKey, string[]> = {
  '/workbench': [ROLES.reviewer],
  '/monitor': [ROLES.reviewer, ROLES.policyAdmin, ROLES.systemAdmin],
  '/policy': [ROLES.policyAdmin, ROLES.systemAdmin],
  '/appeals': [ROLES.reviewer, ROLES.systemAdmin],
  '/quality': [ROLES.policyAdmin, ROLES.systemAdmin],
}

export function canAccessRoute(path: string, roles: string[]): boolean {
  const route = routeKeyFromPath(path)
  if (!route) return false
  return ROUTE_ACCESS[route].some((role) => roles.includes(role))
}

export function defaultRouteForRoles(roles: string[]): AppRouteKey {
  if (roles.includes(ROLES.reviewer)) return '/workbench'
  if (roles.includes(ROLES.policyAdmin)) return '/policy'
  if (roles.includes(ROLES.systemAdmin)) return '/monitor'
  return '/monitor'
}

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] || role
}

export function routeKeyFromPath(path: string): AppRouteKey | null {
  const clean = path.startsWith('/') ? path : `/${path}`
  const first = `/${clean.split('/').filter(Boolean)[0] || ''}` as AppRouteKey
  return first in ROUTE_ACCESS ? first : null
}
