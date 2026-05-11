import type { SyncStatus } from '../../types/up'
import { triggerSyncRetry } from '../../api/up'

interface Props {
  status: SyncStatus | null
}

export default function SyncStatusBanner({ status }: Props) {
  if (!status) return null
  if (status.state === 'ready') return null

  if (status.state === 'syncing') {
    return (
      <div className="p-3 bg-kraken/10 border border-kraken/30 rounded text-sm text-txt-primary">
        Syncing your UP Bank history… data appears as it streams in.
      </div>
    )
  }

  // error
  return (
    <div className="p-3 bg-loss/10 border border-loss/40 rounded text-sm text-txt-primary flex items-center justify-between">
      <span>UP sync failed: {status.error ?? 'unknown error'}</span>
      <button
        onClick={() => triggerSyncRetry()}
        className="ml-3 px-3 py-1 bg-loss/30 hover:bg-loss/50 rounded text-xs"
      >
        Retry
      </button>
    </div>
  )
}
