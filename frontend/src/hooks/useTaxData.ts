import { useCallback, useEffect, useState } from 'react'
import {
  fetchOverview,
  fetchEntries,
  createEntry as apiCreate,
  updateEntry as apiUpdate,
  deleteEntry as apiDelete,
} from '../api/tax'
import type {
  FYOverview,
  TaxEntry,
  TaxEntryCreate,
  TaxEntryKind,
  TaxEntryUpdate,
} from '../types/tax'

interface UseTaxDataState {
  overview: FYOverview[] | null
  overviewError: string | null
  entriesByFY: Record<string, Partial<Record<TaxEntryKind, TaxEntry[]>>>
}

export function useTaxData() {
  const [state, setState] = useState<UseTaxDataState>({
    overview: null,
    overviewError: null,
    entriesByFY: {},
  })

  const refreshOverview = useCallback(async () => {
    try {
      const data = await fetchOverview()
      setState((s) => ({ ...s, overview: data, overviewError: null }))
    } catch (e) {
      setState((s) => ({ ...s, overviewError: e instanceof Error ? e.message : String(e) }))
    }
  }, [])

  useEffect(() => {
    void refreshOverview()
  }, [refreshOverview])

  const loadEntries = useCallback(async (kind: TaxEntryKind, fy: string): Promise<void> => {
    const entries = await fetchEntries(kind, fy)
    setState((s) => ({
      ...s,
      entriesByFY: {
        ...s.entriesByFY,
        [fy]: { ...s.entriesByFY[fy], [kind]: entries },
      },
    }))
  }, [])

  const createEntry = useCallback(async (kind: TaxEntryKind, payload: TaxEntryCreate): Promise<TaxEntry> => {
    const entry = await apiCreate(kind, payload)
    setState((s) => {
      const fyBucket = s.entriesByFY[entry.financial_year] ?? {}
      const list = fyBucket[kind] ?? []
      return {
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [entry.financial_year]: { ...fyBucket, [kind]: [entry, ...list] },
        },
      }
    })
    void refreshOverview()
    return entry
  }, [refreshOverview])

  const updateEntry = useCallback(async (kind: TaxEntryKind, id: string, patch: TaxEntryUpdate): Promise<TaxEntry> => {
    const entry = await apiUpdate(kind, id, patch)
    setState((s) => {
      const newByFY: typeof s.entriesByFY = {}
      for (const fy of Object.keys(s.entriesByFY)) {
        const bucket = s.entriesByFY[fy]
        const list = bucket[kind]
        newByFY[fy] = list ? { ...bucket, [kind]: list.filter((e) => e.id !== id) } : bucket
      }
      const targetBucket = newByFY[entry.financial_year] ?? {}
      const list = targetBucket[kind] ?? []
      newByFY[entry.financial_year] = { ...targetBucket, [kind]: [entry, ...list] }
      return { ...s, entriesByFY: newByFY }
    })
    void refreshOverview()
    return entry
  }, [refreshOverview])

  const deleteEntry = useCallback(async (kind: TaxEntryKind, id: string, fy: string): Promise<void> => {
    let snapshot: TaxEntry[] | undefined
    setState((s) => {
      const fyBucket = s.entriesByFY[fy] ?? {}
      snapshot = fyBucket[kind]
      return {
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [fy]: { ...fyBucket, [kind]: (snapshot ?? []).filter((e) => e.id !== id) },
        },
      }
    })
    try {
      await apiDelete(kind, id)
      void refreshOverview()
    } catch (e) {
      // Restore optimistic delete
      setState((s) => ({
        ...s,
        entriesByFY: {
          ...s.entriesByFY,
          [fy]: { ...s.entriesByFY[fy], [kind]: snapshot ?? [] },
        },
      }))
      throw e
    }
  }, [refreshOverview])

  return {
    overview: state.overview,
    overviewError: state.overviewError,
    entriesByFY: state.entriesByFY,
    refreshOverview,
    loadEntries,
    createEntry,
    updateEntry,
    deleteEntry,
  }
}
