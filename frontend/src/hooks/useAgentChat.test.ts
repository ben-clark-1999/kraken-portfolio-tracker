/**
 * Tests for useAgentChat — the agent WebSocket state machine.
 *
 * We mock WebSocket directly. The hook never sees a real socket.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentChat } from './useAgentChat'

class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  readyState = MockWebSocket.OPEN
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  sent: string[] = []
  url: string

  constructor(url: string) {
    this.url = url
    // Simulate immediate open
    setTimeout(() => this.onopen?.(new Event('open')), 0)
  }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = MockWebSocket.CLOSED }
  receive(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent)
  }
}

let lastSocket: MockWebSocket | null = null

beforeEach(() => {
  lastSocket = null
  const MockWS = vi.fn().mockImplementation((url: string) => {
    lastSocket = new MockWebSocket(url)
    return lastSocket
  })
  // Expose the static constants the hook reads at runtime (e.g. WebSocket.OPEN)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(MockWS as any).OPEN = MockWebSocket.OPEN
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(MockWS as any).CLOSED = MockWebSocket.CLOSED
  // @ts-expect-error — overriding global WebSocket with mock constructor
  globalThis.WebSocket = MockWS
  globalThis.localStorage.clear()
  // Stub fetch (used by apiFetch for rehydration) so it doesn't try to hit the network
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ messages: [] }),
  }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function flush() {
  await act(async () => { await new Promise(r => setTimeout(r, 20)) })
}

describe('useAgentChat', () => {
  it('accumulates token chunks into a single assistant message', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({ type: 'token', content: 'Hello ' }))
    act(() => lastSocket!.receive({ type: 'token', content: 'world.' }))
    expect(result.current.messages.length).toBe(1)
    expect(result.current.messages[0].content).toBe('Hello world.')
    expect(result.current.messages[0].streaming).toBe(true)
  })

  it('clears streaming flag on message_complete', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    await act(async () => {
      lastSocket!.receive({ type: 'token', content: 'Hi.' })
      // Yield so React flushes the token state update and writes currentAssistantId.current
      await new Promise(r => setTimeout(r, 0))
      lastSocket!.receive({ type: 'message_complete' })
    })
    expect(result.current.messages[0].streaming).toBe(false)
    expect(result.current.thinking).toBe(false)
  })

  it('tracks tool_start and tool_end activities', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({
      type: 'tool_start', tool: 'get_portfolio_summary', params: {},
    }))
    expect(result.current.activeTools).toHaveLength(1)
    act(() => lastSocket!.receive({
      type: 'tool_end', tool: 'get_portfolio_summary', duration_ms: 150,
    }))
    expect(result.current.activeTools).toHaveLength(0)
  })

  it('handles HITL request and clears it on respond', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({
      type: 'hitl_request',
      tool: 'get_buy_and_hold_comparison',
      params: { asset: 'ETH' },
      reason: 'Expensive call',
      estimated_duration_ms: 8000,
    }))
    expect(result.current.hitl).not.toBeNull()
    expect(result.current.hitl?.tool).toBe('get_buy_and_hold_comparison')

    act(() => result.current.respondHITL(true))
    expect(result.current.hitl).toBeNull()
    // Verify approval was sent over the wire
    expect(lastSocket!.sent.at(-1)).toContain('"approved":true')
  })

  it('responds to ping with pong', async () => {
    renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    const before = lastSocket!.sent.length
    act(() => lastSocket!.receive({ type: 'ping' }))
    expect(lastSocket!.sent[before]).toContain('"type":"pong"')
  })

  it('appends an error message and clears thinking on error', async () => {
    const { result } = renderHook(() => useAgentChat())
    await flush()
    act(() => lastSocket!.receive({ type: 'session_started', session_id: 'abc' }))
    act(() => lastSocket!.receive({ type: 'agent_thinking' }))
    act(() => lastSocket!.receive({
      type: 'error', error_type: 'model', content: 'The agent ran into an internal error.',
    }))
    expect(result.current.thinking).toBe(false)
    const last = result.current.messages.at(-1)
    expect(last?.content).toContain('Something went wrong')
    expect(last?.content).not.toContain('agent_thinking')
  })
})
