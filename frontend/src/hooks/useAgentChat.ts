import { useState, useCallback, useRef, useEffect } from 'react'
import type { AgentMessage, ToolActivity, HITLState, ServerMessage, ClientMessage } from '../types/agent'
import { apiFetch } from '../api/client'

const SESSION_KEY = 'agent_session_id'
const REHYDRATE_URL = '/api/agent/sessions'

interface UseAgentChatReturn {
  messages: AgentMessage[]
  activeTools: ToolActivity[]
  hitl: HITLState | null
  thinking: boolean
  connected: boolean
  sessionId: string | null
  send: (content: string) => void
  respondHITL: (approved: boolean) => void
  newConversation: () => void
}

export function useAgentChat(): UseAgentChatReturn {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [activeTools, setActiveTools] = useState<ToolActivity[]>([])
  const [hitl, setHitl] = useState<HITLState | null>(null)
  const [thinking, setThinking] = useState(false)
  const [connected, setConnected] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const currentAssistantId = useRef<string | null>(null)

  // ── WebSocket connection ─────────────────────────────────────────

  const connect = useCallback((sid?: string) => {
    const params = sid ? `?session_id=${sid}` : ''
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/agent/chat${params}`)

    ws.onopen = () => setConnected(true)
    ws.onclose = (event) => {
      setConnected(false)
      // Skip reconnect on auth-required close (server told us we're not authenticated)
      if (event.code === 4401) return
      // Reconnect after 2s
      setTimeout(() => {
        const storedSid = localStorage.getItem(SESSION_KEY)
        if (storedSid) connect(storedSid)
      }, 2000)
    }

    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data)
      handleServerMessage(msg)
    }

    wsRef.current = ws
  }, [])

  // ── Message handling ─────────────────────────────────────────────

  const handleServerMessage = useCallback((msg: ServerMessage) => {
    switch (msg.type) {
      case 'session_started':
      case 'session_resumed':
        setSessionId(msg.session_id)
        localStorage.setItem(SESSION_KEY, msg.session_id)
        if (msg.type === 'session_resumed') {
          // Rehydrate messages
          apiFetch(`${REHYDRATE_URL}/${msg.session_id}/messages`)
            .then((r) => r.json())
            .then((data) => {
              const hydrated: AgentMessage[] = data.messages.map(
                (m: { role: string; content: string }, i: number) => ({
                  id: `rehydrated-${i}`,
                  role: m.role as 'user' | 'assistant',
                  content: m.content,
                  streaming: false,
                })
              )
              setMessages(hydrated)
            })
            .catch(() => {})
        }
        break

      case 'agent_thinking':
        setThinking(true)
        break

      case 'classifier_result':
        // Could display in UI — for now just log
        break

      case 'token': {
        setThinking(false)
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.id === currentAssistantId.current && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + msg.content },
            ]
          }
          const newId = `assistant-${Date.now()}`
          currentAssistantId.current = newId
          return [
            ...prev,
            { id: newId, role: 'assistant', content: msg.content, streaming: true },
          ]
        })
        break
      }

      case 'tool_start':
        setActiveTools((prev) => [
          ...prev,
          { tool: msg.tool, params: msg.params, duration_ms: null },
        ])
        break

      case 'tool_end':
        setActiveTools((prev) =>
          prev.filter((t) => t.tool !== msg.tool)
        )
        break

      case 'hitl_request':
        setThinking(false)
        setHitl({
          pending: true,
          tool: msg.tool,
          params: msg.params,
          reason: msg.reason,
          estimated_duration_ms: msg.estimated_duration_ms,
        })
        break

      case 'message_complete':
        setThinking(false)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentAssistantId.current ? { ...m, streaming: false } : m
          )
        )
        currentAssistantId.current = null
        break

      case 'error':
        setThinking(false)
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: `Something went wrong: ${msg.content}`,
            streaming: false,
          },
        ])
        break

      case 'ping':
        wsRef.current?.send(JSON.stringify({ type: 'pong' } satisfies ClientMessage))
        break
    }
  }, [])

  // ── Actions ──────────────────────────────────────────────────────

  const send = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: 'user', content, streaming: false },
    ])
    const msg: ClientMessage = { type: 'user_message', content }
    wsRef.current.send(JSON.stringify(msg))
  }, [])

  const respondHITL = useCallback((approved: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setHitl(null)
    const msg: ClientMessage = { type: 'hitl_response', approved }
    wsRef.current.send(JSON.stringify(msg))
  }, [])

  const newConversation = useCallback(() => {
    setMessages([])
    setActiveTools([])
    setHitl(null)
    setThinking(false)
    currentAssistantId.current = null
    localStorage.removeItem(SESSION_KEY)
    // Reconnect without session_id to get a new one
    wsRef.current?.close()
    connect()
  }, [connect])

  // ── Lifecycle ────────────────────────────────────────────────────

  useEffect(() => {
    const storedSid = localStorage.getItem(SESSION_KEY)
    connect(storedSid || undefined)
    return () => {
      wsRef.current?.close()
    }
  }, [connect])

  return {
    messages,
    activeTools,
    hitl,
    thinking,
    connected,
    sessionId,
    send,
    respondHITL,
    newConversation,
  }
}
