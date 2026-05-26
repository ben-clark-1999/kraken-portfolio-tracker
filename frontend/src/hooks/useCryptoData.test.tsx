import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCryptoData } from './useCryptoData'

vi.mock('../api/portfolio', () => ({
  fetchPortfolioSummary: vi.fn(),
  fetchSnapshots: vi.fn(),
  fetchDCAHistory: vi.fn(),
}))

import {
  fetchPortfolioSummary,
  fetchSnapshots,
  fetchDCAHistory,
} from '../api/portfolio'

beforeEach(() => {
  vi.resetAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useCryptoData', () => {
  it('populates state from three successful fetches', async () => {
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 6000, positions: [] })
    ;(fetchSnapshots as any).mockResolvedValue([{ captured_at: '2026-05-26', total_value_aud: 6000 }])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())

    await waitFor(() => expect(result.current.summary).not.toBeNull())
    expect(result.current.snapshots).toHaveLength(1)
    expect(result.current.errors).toEqual({})
  })

  it('records per-fetch error without crashing', async () => {
    ;(fetchPortfolioSummary as any).mockRejectedValue(new Error('boom'))
    ;(fetchSnapshots as any).mockResolvedValue([])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())

    await waitFor(() => expect(result.current.errors.summary).toBe('boom'))
    expect(result.current.summary).toBeNull()
  })

  it('refresh() triggers a refetch', async () => {
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 1, positions: [] })
    ;(fetchSnapshots as any).mockResolvedValue([])
    ;(fetchDCAHistory as any).mockResolvedValue([])

    const { result } = renderHook(() => useCryptoData())
    await waitFor(() => expect(result.current.summary?.total_value_aud).toBe(1))
    ;(fetchPortfolioSummary as any).mockResolvedValue({ total_value_aud: 2, positions: [] })
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.summary?.total_value_aud).toBe(2)
  })
})
