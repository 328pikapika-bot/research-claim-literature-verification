const SESSION_KEY = 'cca_user_session'
const FALLBACK_SCOPE_KEY = 'claim_consistency_local_user_scope'
const FALLBACK_NAME_KEY = 'claim_consistency_local_user_name'

export interface UserIdentity {
  userId: string
  username: string
}

export function getUserIdentity(): UserIdentity {
  const params = new URLSearchParams(window.location.search)
  const queryUser = params.get('userId')?.trim()
  if (queryUser) {
    return { userId: queryUser, username: queryUser }
  }

  const session = loadSession()
  const sessionUser = session?.user
  const sessionUserId = normalize(sessionUser?.userId || sessionUser?.id)
  if (sessionUserId) {
    return {
      userId: sessionUserId,
      username: normalize(sessionUser?.username || sessionUser?.name) || sessionUserId,
    }
  }

  const pendingUser = normalize(localStorage.getItem('claim_consistency_pending_user_scope'))
  if (pendingUser) {
    return { userId: pendingUser, username: pendingUser }
  }

  const fallbackUser = normalize(localStorage.getItem(FALLBACK_SCOPE_KEY))
  if (fallbackUser) {
    return {
      userId: fallbackUser,
      username: normalize(localStorage.getItem(FALLBACK_NAME_KEY)) || fallbackUser,
    }
  }

  const generated = `local_${cryptoRandom()}`
  localStorage.setItem(FALLBACK_SCOPE_KEY, generated)
  localStorage.setItem(FALLBACK_NAME_KEY, '本地用户')
  return { userId: generated, username: '本地用户' }
}

export function updateLocalIdentity(username: string): UserIdentity {
  const current = getUserIdentity()
  const nextName = normalize(username) || current.username
  localStorage.setItem(FALLBACK_SCOPE_KEY, current.userId)
  localStorage.setItem(FALLBACK_NAME_KEY, nextName)
  return { userId: current.userId, username: nextName }
}

export function getUserScope(): string {
  return getUserIdentity().userId
}

export function isAuthenticated(): boolean {
  return Boolean(getUserIdentity().userId)
}

function loadSession(): Record<string, any> | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function normalize(value: unknown): string {
  return String(value || '').trim()
}

function cryptoRandom(): string {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replace(/-/g, '').slice(0, 12)
  }
  return `${Date.now()}${Math.random().toString(36).slice(2, 8)}`
}
