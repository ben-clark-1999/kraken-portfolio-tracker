import { useState, type FormEvent } from 'react'

import { LoginError, login } from '../api/auth'
import AtmospherePane from '../components/AtmospherePane'

interface Props {
  onAuthenticated: () => void
}

export default function Login({ onAuthenticated }: Props) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [errorFlashing, setErrorFlashing] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!password || submitting) return

    setSubmitting(true)
    setError(null)
    try {
      await login(password)
      onAuthenticated()
    } catch (err) {
      const message = err instanceof LoginError ? err.message : "Couldn't reach server. Try again."
      setError(message)
      setErrorFlashing(true)
      setTimeout(() => setErrorFlashing(false), 1500)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid md:grid-cols-2 min-h-screen animate-fade-in">
      {/* Form pane */}
      <div
        className="flex items-center justify-center px-6 py-10"
        style={{ background: 'linear-gradient(135deg, #0f0e14 0%, #131220 100%)' }}
      >
        <form onSubmit={handleSubmit} className="w-full max-w-[320px] flex flex-col gap-6">
          <h1 className="text-lg font-semibold text-txt-primary tracking-tight">Sign in</h1>

          <div className="flex flex-col gap-1">
            <input
              type="password"
              autoFocus
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              placeholder="Password"
              className={`bg-surface-raised border rounded-md px-3 py-2.5 text-sm text-txt-primary placeholder:text-txt-muted focus:border-kraken focus:outline-none transition-colors ${
                errorFlashing ? 'border-loss' : 'border-surface-border'
              }`}
            />
            {error && <p className="text-xs text-loss mt-1">{error}</p>}
          </div>

          <button
            type="submit"
            disabled={!password || submitting}
            className="bg-kraken hover:bg-kraken-light active:scale-[0.98] text-txt-primary px-3 py-2.5 rounded-md text-sm font-medium transition disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {submitting ? 'Signing in…' : 'Continue'}
          </button>
        </form>
      </div>

      {/* Atmosphere pane (hidden < 768px) */}
      <AtmospherePane />
    </div>
  )
}
