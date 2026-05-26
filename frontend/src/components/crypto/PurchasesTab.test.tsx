import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

import PurchasesTab from './PurchasesTab'

const apiFetch = vi.fn()

vi.mock('../../api/client', () => ({
  apiFetch: (...args: any[]) => apiFetch(...args),
  UNAUTHORIZED_EVENT: 'auth:unauthorized',
  SERVER_ERROR_EVENT: 'server:error',
}))

beforeEach(() => {
  apiFetch.mockReset()
})

describe('PurchasesTab Sync-now button', () => {
  it('renders empty placeholder when there are no entries', () => {
    render(<PurchasesTab entries={[]} onSynced={() => Promise.resolve()} dcaError={undefined} />)
    expect(screen.getByText(/no purchases recorded yet/i)).toBeInTheDocument()
  })

  it('POSTs /api/sync and shows success status', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ synced: 3, last_trade_id: 'T123' }),
    })
    const onSynced = vi.fn(() => Promise.resolve())
    render(<PurchasesTab entries={[]} onSynced={onSynced} dcaError={undefined} />)
    fireEvent.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() => expect(onSynced).toHaveBeenCalled())
    expect(apiFetch).toHaveBeenCalledWith('/api/sync', { method: 'POST' })
    expect(await screen.findByText(/synced 3 new purchases/i)).toBeInTheDocument()
  })

  it('shows error inline when sync fails', async () => {
    apiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
      statusText: 'Server Error',
    })
    render(<PurchasesTab entries={[]} onSynced={() => Promise.resolve()} dcaError={undefined} />)
    fireEvent.click(screen.getByRole('button', { name: /sync now/i }))
    expect(await screen.findByText(/sync failed/i)).toBeInTheDocument()
  })
})
