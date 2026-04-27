import type { ServerErrorDetail } from '../api/client'

interface Props {
  detail: ServerErrorDetail
  onRetry: () => void
  onDismiss: () => void
}

export default function ErrorBanner({ detail, onRetry, onDismiss }: Props) {
  return (
    <div
      className="bg-loss/10 border-b border-loss/20 px-6 py-2 text-sm text-loss"
      role="alert"
      aria-live="polite"
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <span>Something went wrong. Please retry.</span>
          <span className="text-xs text-txt-muted font-mono">
            req {detail.requestId.slice(0, 8)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="px-3 py-1 bg-loss/20 hover:bg-loss/30 active:scale-[0.97] text-loss rounded text-xs font-medium transition-[colors,transform]"
          >
            Retry
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="text-xs text-txt-muted hover:text-txt-secondary transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}
