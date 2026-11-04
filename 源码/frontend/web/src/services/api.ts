import { requireUserScope } from './nstlAuth'

const RAW_BASE = import.meta.env.VITE_API_BASE_URL || ''
export const API_BASE = RAW_BASE.replace(/\/$/, '')

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {})
  headers.set('X-User-Scope', await requireUserScope())
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const detail = await parseError(response)
    throw new Error(detail || `Request failed: ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    const detail = payload?.detail || payload?.message
    return typeof detail === 'string' ? detail : JSON.stringify(payload)
  } catch {
    return response.text()
  }
}
