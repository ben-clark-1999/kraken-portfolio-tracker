import { useEffect, useState, useRef } from 'react'
import { fetchSyncStatus } from '../api/up'
import type { SyncStatus } from '../types/up'

const POLL_INTERVAL_MS = 10_000

export function useUpSyncStatus() {
  const [status, setStatus] = useState<SyncStatus | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    cancelledRef.current = false
    let timer: ReturnType<typeof setTimeout> | null = null

    async function poll() {
      try {
        const s = await fetchSyncStatus()
        if (cancelledRef.current) return
        setStatus(s)
        if (s.state === 'syncing') {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        // silent — banner stays in last known state
      }
    }

    poll()

    return () => {
      cancelledRef.current = true
      if (timer) clearTimeout(timer)
    }
  }, [])

  return status
}
