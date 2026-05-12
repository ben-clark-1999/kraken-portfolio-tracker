import { useEffect, useState, useCallback } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { UNAUTHORIZED_EVENT } from './api/client'
import { me } from './api/auth'
import AppLayout from './components/AppLayout'
import CombinedPage from './pages/CombinedPage'
import CryptoPage from './pages/CryptoPage'
import UpPage from './pages/UpPage'
import StrategiesPage from './pages/StrategiesPage'
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
          <Route path="/" element={<Navigate to="/combined" replace />} />
          <Route path="/combined" element={<CombinedPage />} />
          <Route path="/crypto" element={<CryptoPage onSignedOut={() => setAuth('unauthenticated')} />} />
          <Route path="/up" element={<UpPage />} />
          <Route path="/strategies" element={<StrategiesPage />} />
          <Route path="*" element={<Navigate to="/combined" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}
