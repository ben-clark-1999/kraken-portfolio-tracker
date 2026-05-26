import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import DCAHistoryTable from '../DCAHistoryTable'
import { apiFetch } from '../../api/client'
import type { DCAEntry } from '../../types'

type SyncStatus =
  | { kind: 'idle' }
  | { kind: 'syncing' }
  | { kind: 'success'; synced: number; at: Date }
  | { kind: 'error'; message: string }

interface Props {
  entries: DCAEntry[]
  onSynced: () => Promise<void>
  dcaError: string | undefined
}

export default function PurchasesTab({ entries, onSynced, dcaError }: Props) {
  const [status, setStatus] = useState<SyncStatus>({ kind: 'idle' })

  async function handleSync() {
    setStatus({ kind: 'syncing' })
    try {
      const res = await apiFetch('/api/sync', { method: 'POST' })
      if (!res.ok) {
        setStatus({ kind: 'error', message: `Sync failed (${res.status} ${res.statusText})` })
        return
      }
      const body = (await res.json()) as { synced?: number }
      await onSynced()
      setStatus({ kind: 'success', synced: body.synced ?? 0, at: new Date() })
    } catch (err) {
      setStatus({ kind: 'error', message: `Sync failed: ${(err as Error).message}` })
    }
  }

  const isSyncing = status.kind === 'syncing'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-txt-muted">All purchases synced from Kraken.</p>
        <div className="flex items-center gap-3">
          <SyncStatusLabel status={status} />
          <button
            type="button"
            onClick={handleSync}
            disabled={isSyncing}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-surface-raised border border-surface-border text-sm text-txt-primary hover:bg-surface-hover transition-colors duration-200 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
            {isSyncing ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
      </div>

      {dcaError ? (
        <div
          className="text-base text-loss bg-surface-raised border border-surface-border rounded-lg p-6"
          role="status"
          aria-live="polite"
        >
          Previous purchases unavailable: {dcaError}
        </div>
      ) : entries.length === 0 ? (
        <div className="text-center py-12 bg-surface-raised border border-surface-border rounded-xl">
          <p className="text-txt-muted">No purchases recorded yet.</p>
          <p className="text-sm text-txt-muted mt-1">Click Sync now to pull from Kraken.</p>
        </div>
      ) : (
        <DCAHistoryTable entries={entries} />
      )}
    </div>
  )
}

function SyncStatusLabel({ status }: { status: SyncStatus }) {
  if (status.kind === 'success') {
    return (
      <span className="text-xs text-profit">
        Synced {status.synced} new purchases · just now
      </span>
    )
  }
  if (status.kind === 'error') {
    return <span className="text-xs text-loss">{status.message}</span>
  }
  return null
}
