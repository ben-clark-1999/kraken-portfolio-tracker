/**
 * Shared fetch wrapper. Always sends cookies, dispatches a global event on 401
 * so the App component can flip auth state regardless of which call triggered it.
 */

export const UNAUTHORIZED_EVENT = 'auth:unauthorized'

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
  }

  return response
}
