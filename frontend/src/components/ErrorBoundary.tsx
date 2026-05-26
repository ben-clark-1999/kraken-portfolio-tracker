import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI crashed:', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="min-h-screen bg-surface text-txt-primary font-sans flex items-center justify-center px-6">
        <div className="max-w-lg w-full bg-surface-raised border border-surface-border rounded-lg p-6 space-y-4">
          <h1 className="text-lg font-semibold">Something broke in the UI</h1>
          <pre className="text-xs text-txt-muted whitespace-pre-wrap break-words">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            className="text-sm px-3 py-1.5 rounded bg-surface-border hover:bg-surface-border/80"
            onClick={() => {
              this.setState({ error: null })
              window.location.reload()
            }}
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
