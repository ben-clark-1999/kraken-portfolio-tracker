import { useEffect, useState, useCallback } from 'react'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'

type AuthState = 'checking' | 'authenticated' | 'unauthenticated'

export default function App() {
  const [auth, setAuth] = useState<AuthState>('checking')

  const refreshAuth = useCallback(async () => {
    try {
      const ok = await me()
      setAuth(ok ? 'authenticated' : 'unauthenticated')
    } catch {
      setAuth('unauthenticated')
    }
  }, [])

  // Initial check on mount
  useEffect(() => {
    refreshAuth()
  }, [refreshAuth])

  // Listen for global 401 events (any API call returning 401 fires this)
  useEffect(() => {
    function handleUnauthorized() {
      setAuth('unauthenticated')
    }
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [])

  if (auth === 'checking') {
    return <div className="min-h-screen bg-surface" />
  }

  if (auth === 'unauthenticated') {
    return <Login onAuthenticated={() => setAuth('authenticated')} />
  }

  return <Dashboard onSignedOut={() => setAuth('unauthenticated')} />
}
