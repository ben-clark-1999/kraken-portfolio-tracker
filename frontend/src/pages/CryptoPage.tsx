import { useEffect, useState } from 'react'
import { useCryptoData } from '../hooks/useCryptoData'
import CryptoTabBar, { useActiveTab } from '../components/crypto/CryptoTabBar'
import BalanceTab from '../components/crypto/BalanceTab'
import AssetsTab from '../components/crypto/AssetsTab'
import PurchasesTab from '../components/crypto/PurchasesTab'
import AskTab from '../components/crypto/AskTab'
import SignOutButton from '../components/SignOutButton'
import ErrorBanner from '../components/ErrorBanner'
import { SERVER_ERROR_EVENT, type ServerErrorDetail } from '../api/client'

interface Props {
  onSignedOut: () => void
}

export default function CryptoPage({ onSignedOut }: Props) {
  const data = useCryptoData()
  const { active, setActive } = useActiveTab()
  const [serverError, setServerError] = useState<ServerErrorDetail | null>(null)

  useEffect(() => {
    function handle(e: Event) {
      setServerError((e as CustomEvent<ServerErrorDetail>).detail)
    }
    window.addEventListener(SERVER_ERROR_EVENT, handle)
    return () => window.removeEventListener(SERVER_ERROR_EVENT, handle)
  }, [])

  useEffect(() => {
    // ⌘K / Ctrl+K jumps to the Ask AI tab. The hero input there has
    // autoFocus, so this both navigates and gives focus in one keypress.
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setActive('ask')
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [setActive])

  return (
    <div className="min-h-screen bg-surface text-txt-primary font-sans">
      <div className="px-8 pt-6">
        <div className="w-full max-w-[1600px] mx-auto flex items-center justify-end">
          <SignOutButton onSignedOut={onSignedOut} />
        </div>
      </div>

      {serverError && (
        <ErrorBanner
          detail={serverError}
          onRetry={() => {
            setServerError(null)
            data.refresh()
          }}
          onDismiss={() => setServerError(null)}
        />
      )}

      <div className="w-full max-w-[1600px] mx-auto px-8 pt-6">
        <CryptoTabBar />
      </div>

      <div className="w-full max-w-[1600px] mx-auto px-8 py-8">
        {active === 'balance' && (
          <BalanceTab
            summary={data.summary}
            snapshots={data.snapshots}
            refreshing={data.refreshing}
            onRefresh={data.refresh}
            summaryError={data.errors.summary}
            snapshotsError={data.errors.snapshots}
          />
        )}
        {active === 'assets' && (
          <AssetsTab
            summary={data.summary}
            snapshots={data.snapshots}
            summaryError={data.errors.summary}
          />
        )}
        {active === 'purchases' && (
          <PurchasesTab
            entries={data.dcaHistory}
            onSynced={data.refresh}
            dcaError={data.errors.dca}
          />
        )}
        {active === 'ask' && <AskTab />}
      </div>
    </div>
  )
}
