import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './globals.css'
import Dashboard from './pages/Dashboard'

document.documentElement.classList.add('dark')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Dashboard />
  </StrictMode>,
)
