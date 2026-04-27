/**
 * Shared fetch wrapper. Always sends cookies. Dispatches:
 *  - UNAUTHORIZED_EVENT on 401 (auth state machine listens)
 *  - SERVER_ERROR_EVENT on 5xx (Dashboard listens, renders ErrorBanner)
 */

export const UNAUTHORIZED_EVENT = 'auth:unauthorized'
export const SERVER_ERROR_EVENT = 'server:error'

export interface ServerErrorDetail {
  requestId: string
  status: number
}

export async function apiFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
  } else if (response.status >= 500 && response.status < 600) {
    const detail: ServerErrorDetail = {
      requestId: response.headers.get('X-Request-ID') ?? 'unknown',
      status: response.status,
    }
    window.dispatchEvent(new CustomEvent<ServerErrorDetail>(SERVER_ERROR_EVENT, { detail }))
  }

  return response
}
