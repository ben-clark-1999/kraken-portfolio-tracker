// ── Server → Client messages ───────────────────────────────────────────

export type ServerMessage =
  | { type: 'session_started'; session_id: string }
  | { type: 'session_resumed'; session_id: string }
  | { type: 'agent_thinking' }
  | { type: 'classifier_result'; primary_category: string; confidence: number }
  | { type: 'token'; content: string }
  | { type: 'tool_start'; tool: string; params: Record<string, unknown> }
  | { type: 'tool_end'; tool: string; duration_ms: number }
  | { type: 'hitl_request'; tool: string; params: Record<string, unknown>; reason: string; estimated_duration_ms: number }
  | { type: 'message_complete' }
  | { type: 'error'; error_type: string; content: string }
  | { type: 'ping' }
  | { type: 'pong' }

// ── Client → Server messages ───────────────────────────────────────────

export type ClientMessage =
  | { type: 'user_message'; content: string }
  | { type: 'hitl_response'; approved: boolean }
  | { type: 'ping' }
  | { type: 'pong' }

// ── UI state ───────────────────────────────────────────────────────────

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** True while tokens are still streaming in */
  streaming: boolean
}

export interface ToolActivity {
  tool: string
  params: Record<string, unknown>
  /** null while in progress */
  duration_ms: number | null
}

export interface HITLState {
  pending: boolean
  tool: string
  params: Record<string, unknown>
  reason: string
  estimated_duration_ms: number
}
