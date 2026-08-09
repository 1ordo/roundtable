export type MeUser = {
  id: string
  username: string
  handle?: string | null
  display_name?: string | null
  email: string | null
  role: 'admin' | 'member'
  avatar_path: string | null
  country_code: string | null
  services: number[]
  // public | friends | private. Replaced the old is_public flag.
  visibility: string
  countries: string[]
  prefs: {
    languages?: string[]
    genres?: number[]
    parents_guide?: boolean
    discovery?: string
    hide_watched?: boolean
    /** Suggest only what is on a service they subscribe to. */
    only_my_services?: boolean
    default_type?: string
    notify_kinds?: string[]
    reduce_motion?: boolean
    countries?: string[]
    panel_visibility?: Record<string, string>
    email_alerts?: boolean
    /** A word when a paid service goes a month unused. Opt-in. */
    expense_alerts?: boolean
  }
}

export type Me = {
  user: MeUser
  csrf: string
  needs_onboarding: boolean
}

let csrfToken: string | null = null

/* The token the session issued, for callers that build their own request.
   Streaming endpoints cannot go through `request` because they read the
   body incrementally rather than as one JSON payload. */
export function currentCsrf(): string | null {
  return csrfToken
}

/* A session that expires while a tab is open used to leave the person on a
   signed-in shell where every query failed with an unexplained error. One
   redirect, guarded so a page full of failing queries does not fire it
   repeatedly, and carrying where they were so they land back there. */
let redirecting = false

function sessionExpired(): void {
  if (redirecting) return
  if (window.location.pathname.startsWith('/login')) return
  redirecting = true
  csrfToken = null
  const next = window.location.pathname + window.location.search
  window.location.assign(`/login?next=${encodeURIComponent(next)}`)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function fetchMe(): Promise<Me | null> {
  const resp = await fetch('/api/me')
  if (resp.status === 401) return null
  if (!resp.ok) throw new ApiError(resp.status, 'could not load your profile')
  const me = (await resp.json()) as Me
  csrfToken = me.csrf
  return me
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (csrfToken && method !== 'GET') headers['X-CSRF-Token'] = csrfToken
  const resp = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!resp.ok) {
    let detail = 'request failed'
    try {
      detail = ((await resp.json()) as { detail?: string }).detail ?? detail
    } catch {
      // response had no JSON body, keep the generic message
    }
    if (resp.status === 401) sessionExpired()
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}

export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = {}
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  const resp = await fetch(path, { method: 'POST', headers, body: form })
  if (!resp.ok) {
    let detail = 'upload failed'
    try {
      detail = ((await resp.json()) as { detail?: string }).detail ?? detail
    } catch {
      // no JSON body
    }
    throw new ApiError(resp.status, detail)
  }
  return (await resp.json()) as T
}

export async function logout(): Promise<void> {
  await api.post('/api/auth/logout')
  csrfToken = null
}
