import { useEffect, useState, useCallback } from 'react'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import SideRail from './components/SideRail'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import TaxHub from './pages/TaxHub'

type AuthState = 'checking' | 'authenticated' | 'unauthenticated'

export default function App() {
  const [auth, setAuth] = useState<AuthState>('checking')
  const [view, setView] = useState<'dashboard' | 'tax'>('dashboard')

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

  const onSignedOut = () => setAuth('unauthenticated')

  return (
    <div className="flex min-h-screen bg-surface">
      <SideRail view={view} onChangeView={setView} onSignedOut={onSignedOut} />
      {view === 'dashboard' ? (
        <Dashboard onSignedOut={onSignedOut} />
      ) : (
        <TaxHub />
      )}
    </div>
  )
}
