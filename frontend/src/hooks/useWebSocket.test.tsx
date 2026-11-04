/** @vitest-environment jsdom */
/**
 * useWebSocket lifecycle (UI E2E suite, #769).
 *
 * The production bundle mounts once, so the Playwright tier cannot reach the
 * "closed while still connecting" path; React StrictMode in dev (main.tsx) mounts, unmounts and
 * remounts every effect, so the cleanup closes a socket that is still CONNECTING. Browsers log
 * "WebSocket is closed before the connection is established" when close() runs in that state —
 * the bug class the gallery hit in synthet/image-scoring-gallery#230.
 */
import { StrictMode, type ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useWebSocket } from './useWebSocket'
import { useWsStore } from '@/stores/wsStore'

class FakeSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: FakeSocket[] = []
  readyState = FakeSocket.CONNECTING
  closedWhileConnecting = false
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }
  close() {
    if (this.readyState === FakeSocket.CONNECTING) this.closedWhileConnecting = true
    if (this.readyState === FakeSocket.CLOSED) return
    this.readyState = FakeSocket.CLOSED
    this.onclose?.()
  }
  open() {
    this.readyState = FakeSocket.OPEN
    this.onopen?.()
  }
  /** Failed handshake as browsers do it: readyState is CLOSED before `error`, then `close` fires. */
  fail() {
    this.readyState = FakeSocket.CLOSED
    this.onerror?.()
    this.onclose?.()
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
  useWsStore.setState({ connectionStatus: 'connecting', wasEverLive: false })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useWebSocket', () => {
  it('connects to /ws/updates and goes live on open', () => {
    renderHook(() => useWebSocket())
    expect(FakeSocket.instances).toHaveLength(1)
    expect(FakeSocket.instances[0].url).toMatch(/\/ws\/updates$/)
    FakeSocket.instances[0].open()
    expect(useWsStore.getState().connectionStatus).toBe('live')
  })

  it('reconnects after a live socket closes', () => {
    renderHook(() => useWebSocket())
    FakeSocket.instances[0].open()
    FakeSocket.instances[0].close()
    expect(useWsStore.getState().connectionStatus).toBe('connecting')
    vi.advanceTimersByTime(2000)
    expect(FakeSocket.instances).toHaveLength(2)
  })

  it('under StrictMode keeps exactly one open socket after the double mount', () => {
    const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>
    renderHook(() => useWebSocket(), { wrapper })
    vi.advanceTimersByTime(10_000)
    const live = FakeSocket.instances.filter((s) => s.readyState !== FakeSocket.CLOSED)
    expect(live).toHaveLength(1)
  })

  it.fails('#774: with every attempt refused, the status reaches offline after INITIAL_OFFLINE_MS', () => {
    renderHook(() => useWebSocket())
    for (let elapsed = 0; elapsed <= 14_000; elapsed += 2000) {
      FakeSocket.instances[FakeSocket.instances.length - 1].fail()
      vi.advanceTimersByTime(2000)
    }
    expect(useWsStore.getState().connectionStatus).toBe('offline')
  })

  it.fails('#773: unmounting while CONNECTING does not call close() on the connecting socket', () => {
    const { unmount } = renderHook(() => useWebSocket())
    unmount()
    expect(FakeSocket.instances[0].closedWhileConnecting).toBe(false)
  })

  it('a failed handshake schedules one reconnect and does not close a connecting socket', () => {
    renderHook(() => useWebSocket())
    FakeSocket.instances[0].fail()
    expect(FakeSocket.instances[0].closedWhileConnecting).toBe(false)
    vi.advanceTimersByTime(2000)
    expect(FakeSocket.instances).toHaveLength(2)
  })
})
