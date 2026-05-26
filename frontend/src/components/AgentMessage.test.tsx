import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import AgentMessage from './AgentMessage'
import type { AgentMessage as AgentMessageType } from '../types/agent'

function assistant(content: string): AgentMessageType {
  return { id: 'a-1', role: 'assistant', content, streaming: false }
}

describe('AgentMessage markdown rendering', () => {
  it('renders pipe-table syntax as a real HTML table', () => {
    const md = [
      '| Asset | Qty | Value |',
      '|-------|-----|-------|',
      '| ETH   | 1.3 | $3,908 |',
    ].join('\n')
    render(<AgentMessage message={assistant(md)} />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('Asset')).toBeInTheDocument()
    expect(screen.getByText('1.3')).toBeInTheDocument()
  })

  it('renders **bold** as <strong>', () => {
    render(<AgentMessage message={assistant('hello **world**')} />)
    expect(screen.getByText('world').tagName).toBe('STRONG')
  })

  it('renders headings as the correct tag', () => {
    render(<AgentMessage message={assistant('## Snapshot')} />)
    expect(screen.getByRole('heading', { level: 2, name: 'Snapshot' })).toBeInTheDocument()
  })

  it('renders fenced code blocks inside <pre><code>', () => {
    render(<AgentMessage message={assistant('```\nx=1\n```')} />)
    const code = screen.getByText('x=1')
    expect(code.tagName).toBe('CODE')
    expect(code.closest('pre')).not.toBeNull()
  })

  it('still renders user content as plain text without crashing on non-string', () => {
    const m: AgentMessageType = { id: 'u', role: 'user', content: 'hi', streaming: false }
    render(<AgentMessage message={m} />)
    expect(screen.getByText('hi')).toBeInTheDocument()
  })
})
