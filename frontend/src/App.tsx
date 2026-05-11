import { useEffect, useState, useCallback } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import AppLayout from './components/AppLayout'
import CryptoPage from './pages/CryptoPage'
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

  useEffect(() => { refreshAuth() }, [refreshAuth])

  useEffect(() => {
    function handleUnauthorized() { setAuth('unauthenticated') }
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [])

  if (auth === 'checking') return <div className="min-h-screen bg-surface" />

  if (auth === 'unauthenticated') {
    return <Login onAuthenticated={() => setAuth('authenticated')} />
  }

  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/crypto" replace />} />
          <Route path="/crypto" element={<CryptoPage onSignedOut={() => setAuth('unauthenticated')} />} />
          <Route path="/combined" element={<div className="p-6 text-txt-muted">Combined view — coming in Task 9</div>} />
          <Route path="/up" element={<div className="p-6 text-txt-muted">UP Bank view — coming in Task 8</div>} />
          <Route path="*" element={<Navigate to="/crypto" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}
