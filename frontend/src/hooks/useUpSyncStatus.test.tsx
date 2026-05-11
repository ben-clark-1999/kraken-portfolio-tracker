import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useUpSyncStatus } from './useUpSyncStatus'
import * as upApi from '../api/up'

describe('useUpSyncStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('polls every 10s while state is syncing, stops once ready', async () => {
    const spy = vi.spyOn(upApi, 'fetchSyncStatus')
      .mockResolvedValueOnce({ state: 'syncing', last_synced_at: null, error: null })
      .mockResolvedValueOnce({ state: 'syncing', last_synced_at: null, error: null })
      .mockResolvedValueOnce({ state: 'ready', last_synced_at: '2026-05-11T00:00:00Z', error: null })

    const { result } = renderHook(() => useUpSyncStatus())

    // Flush the initial fetch promise (advance 0ms so no timers fire yet)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    await waitFor(() => expect(result.current?.state).toBe('syncing'))
    expect(spy).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(spy).toHaveBeenCalledTimes(2)

    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    await waitFor(() => expect(result.current?.state).toBe('ready'))
    expect(spy).toHaveBeenCalledTimes(3)

    // Once ready, polling stops
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(spy).toHaveBeenCalledTimes(3)
  })
})
