/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import App from './App'

const featureLoads = vi.hoisted(() => ({ scores: vi.fn(), map: vi.fn() }))
vi.mock('@/features/score-analytics/ScoreAnalyticsPage', () => {
  featureLoads.scores()
  return { ScoreAnalyticsPage: () => <div>Scores feature</div> }
})
vi.mock('@/pages/GeoMapPage', () => {
  featureLoads.map()
  return { GeoMapPage: () => <div>Map feature</div> }
})
vi.mock('@/pages/RunsPage', () => ({ RunsPage: () => <div>Runs destination</div> }))
vi.mock('@/components/layout/Sidebar', () => ({ Sidebar: () => null }))
vi.mock('@/components/layout/ConnectionStatus', () => ({ ConnectionStatus: () => null }))
vi.mock('@/components/scope/ScopeSelector', () => ({ ScopeSelector: () => null }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: () => {} }))
vi.mock('@/hooks/useConfig', () => ({ useConfig: () => ({ isEmbeddingMapEnabled: false, isDbExplorerEnabled: true, isLoading: false }) }))
vi.mock('@/api/runs', () => ({ runsApi: {
  list: async () => [], drive: { status: async () => ({ state: { enabled: false } }) },
} }))

describe('disabled web pages', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it.each(['/ui/scores', '/ui/scores/details', '/ui/map', '/ui/map/details'])('redirects direct access to %s without loading the feature', async (path) => {
    window.history.replaceState({}, '', `${path}?range=all#detail`)
    render(<App />)
    await waitFor(() => expect(window.location.pathname).toBe('/ui/runs'))
    expect(screen.getByText('Runs destination')).toBeTruthy()
    expect(window.location.search).toBe('')
    expect(window.location.hash).toBe('')
    expect(featureLoads.scores).not.toHaveBeenCalled()
    expect(featureLoads.map).not.toHaveBeenCalled()
  })

  it('keeps enabled navigation while hiding Scores and Map', () => {
    window.history.replaceState({}, '', '/ui/runs')
    render(<App />)
    expect(screen.getByRole('link', { name: 'Images' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Scores' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Map' })).toBeNull()
  })
})
