import { apiFetch } from './client'

export class LoginError extends Error {
  retryAfterSeconds?: number

  constructor(message: string, retryAfterSeconds?: number) {
    super(message)
    this.name = 'LoginError'
    this.retryAfterSeconds = retryAfterSeconds
  }
}

export async function login(password: string): Promise<void> {
  const response = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })

  if (response.status === 200) return

  if (response.status === 401) {
    throw new LoginError('Incorrect password')
  }

  if (response.status === 429) {
    const retry = parseInt(response.headers.get('Retry-After') ?? '60', 10)
    throw new LoginError(`Too many attempts. Try again in ${retry} seconds.`, retry)
  }

  throw new LoginError("Couldn't reach server. Try again.")
}

export async function logout(): Promise<void> {
  await apiFetch('/api/auth/logout', { method: 'POST' })
}

export async function me(): Promise<boolean> {
  const response = await apiFetch('/api/auth/me')
  return response.status === 200
}
