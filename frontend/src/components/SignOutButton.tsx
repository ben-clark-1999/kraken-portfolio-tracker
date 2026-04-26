import { useState } from 'react'

import { logout } from '../api/auth'

interface Props {
  onSignedOut: () => void
}

export default function SignOutButton({ onSignedOut }: Props) {
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleClick() {
    setLoggingOut(true)
    try {
      await logout()
    } finally {
      onSignedOut()
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loggingOut}
      className="text-xs text-txt-muted hover:text-txt-secondary transition-colors disabled:opacity-60"
    >
      {loggingOut ? 'Signing out…' : 'Sign out'}
    </button>
  )
}
