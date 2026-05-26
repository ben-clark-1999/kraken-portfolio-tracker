import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const send = vi.fn()
const newConversation = vi.fn()

vi.mock('../../hooks/useAgentChat', () => ({
  useAgentChat: () => ({
    messages: [],
    activeTools: [],
    hitl: null,
    thinking: false,
    connected: true,
    sessionId: null,
    sessions: [],
    refreshSessions: vi.fn(),
    loadSession: vi.fn(),
    send,
    respondHITL: vi.fn(),
    newConversation,
  }),
}))

import AskTab from './AskTab'

describe('AskTab', () => {
  it('renders hero empty state when there are no messages', () => {
    render(<AskTab />)
    expect(screen.getByRole('heading', { name: /how can i help/i })).toBeInTheDocument()
    expect(screen.getByText(/is my portfolio good\?/i)).toBeInTheDocument()
  })

  it('submits a question when a suggestion pill is clicked', () => {
    render(<AskTab />)
    fireEvent.click(screen.getByText(/is my portfolio good\?/i))
    expect(send).toHaveBeenCalledWith('Is my portfolio good?')
  })
})
