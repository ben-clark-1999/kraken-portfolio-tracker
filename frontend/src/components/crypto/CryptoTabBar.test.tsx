import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import CryptoTabBar, { TAB_IDS } from './CryptoTabBar'

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="search">{loc.search}</div>
}

function renderAt(initial = '/crypto') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <CryptoTabBar />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('CryptoTabBar', () => {
  it('renders one tab per known TAB_ID', () => {
    renderAt()
    for (const t of TAB_IDS) {
      expect(screen.getByRole('tab', { name: new RegExp(t.label, 'i') })).toBeInTheDocument()
    }
  })

  it('defaults to Balance when ?tab is missing', () => {
    renderAt('/crypto')
    expect(screen.getByRole('tab', { name: /balance/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('reflects ?tab=ask in the active state', () => {
    renderAt('/crypto?tab=ask')
    expect(screen.getByRole('tab', { name: /ask ai/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('clicking a tab updates ?tab=', () => {
    renderAt('/crypto')
    fireEvent.click(screen.getByRole('tab', { name: /previous purchases/i }))
    expect(screen.getByTestId('search').textContent).toBe('?tab=purchases')
  })

  it('falls back to Balance for an unknown ?tab value', () => {
    renderAt('/crypto?tab=garbage')
    expect(screen.getByRole('tab', { name: /balance/i })).toHaveAttribute('aria-selected', 'true')
  })
})
