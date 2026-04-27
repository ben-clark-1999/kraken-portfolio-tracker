import { apiFetch } from './client'
import type {
  FYOverview,
  TaxAttachment,
  TaxEntry,
  TaxEntryCreate,
  TaxEntryKind,
  TaxEntryUpdate,
} from '../types/tax'
import { KIND_TO_PATH } from '../types/tax'

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText)
    throw new Error(`${response.status}: ${text}`)
  }
  return response.json() as Promise<T>
}

export async function fetchOverview(): Promise<FYOverview[]> {
  const r = await apiFetch('/api/tax/overview')
  return jsonOrThrow<FYOverview[]>(r)
}

export async function fetchEntries(kind: TaxEntryKind, fy: string): Promise<TaxEntry[]> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}?fy=${encodeURIComponent(fy)}`)
  return jsonOrThrow<TaxEntry[]>(r)
}

export async function createEntry(kind: TaxEntryKind, payload: TaxEntryCreate): Promise<TaxEntry> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return jsonOrThrow<TaxEntry>(r)
}

export async function updateEntry(kind: TaxEntryKind, id: string, patch: TaxEntryUpdate): Promise<TaxEntry> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
  return jsonOrThrow<TaxEntry>(r)
}

export async function deleteEntry(kind: TaxEntryKind, id: string): Promise<void> {
  const path = KIND_TO_PATH[kind]
  const r = await apiFetch(`/api/tax/${path}/${id}`, { method: 'DELETE' })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(`${r.status}: ${text}`)
  }
}

export async function uploadAttachment(
  parentKind: TaxEntryKind,
  parentId: string | null,
  file: File,
): Promise<TaxAttachment> {
  const form = new FormData()
  form.append('parent_kind', parentKind)
  if (parentId) form.append('parent_id', parentId)
  form.append('file', file)

  // FormData uploads must NOT set Content-Type — browser builds the boundary
  const r = await fetch('/api/tax/attachments', {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  return jsonOrThrow<TaxAttachment>(r)
}

export async function fetchAttachmentUrl(id: string): Promise<{ url: string; expires_at: string }> {
  const r = await apiFetch(`/api/tax/attachments/${id}/url`)
  return jsonOrThrow<{ url: string; expires_at: string }>(r)
}

export async function deleteAttachment(id: string): Promise<void> {
  const r = await apiFetch(`/api/tax/attachments/${id}`, { method: 'DELETE' })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(`${r.status}: ${text}`)
  }
}
