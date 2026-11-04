import { useEffect, useRef } from 'react'
import { useWsStore } from '@/stores/wsStore'
import { adaptBackendMessage } from '@/utils/adaptBackendMessage'
import type { WsEvent } from '@/types/api'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/updates`
const RECONNECT_DELAY_MS = 2000
/** First visit: stay on Connecting until live or this elapses. */
const INITIAL_OFFLINE_MS = 12_000
/** After a live session drops: show Reconnecting until this elapses without live. */
const RECONNECT_OFFLINE_MS = 15_000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const offlineTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    function clearOfflineTimer() {
      if (offlineTimer.current) {
        clearTimeout(offlineTimer.current)
        offlineTimer.current = null
      }
    }

    /** One timer per outage: retries must not restart it, and only onopen ends it. */
    function markDisconnected() {
      const { connectionStatus, wasEverLive, setConnectionConnecting } = useWsStore.getState()
      if (connectionStatus === 'offline') return
      setConnectionConnecting()
      if (offlineTimer.current) return
      const delay = wasEverLive ? RECONNECT_OFFLINE_MS : INITIAL_OFFLINE_MS
      offlineTimer.current = setTimeout(() => {
        offlineTimer.current = null
        if (cancelled) return
        if (useWsStore.getState().connectionStatus === 'live') return
        useWsStore.getState().setConnectionOffline()
      }, delay)
    }

    function connect() {
      if (cancelled) return
      markDisconnected()
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (cancelled) return
        clearOfflineTimer()
        useWsStore.getState().setConnectionLive()
      }

      ws.onmessage = (ev) => {
        if (cancelled) return
        try {
          const raw = JSON.parse(ev.data as string) as Record<string, unknown>
          const { events, bumpRuns, bumpDrive } = adaptBackendMessage(raw)
          const store = useWsStore.getState()
          if (bumpRuns) store.bumpRunsVersion()
          if (bumpDrive) store.bumpDriveVersion()
          for (const event of events) dispatch(event)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        if (cancelled) return
        markDisconnected()
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    function dispatch(event: WsEvent) {
      const store = useWsStore.getState()
      switch (event.type) {
        case 'run_progress':
          store.setRunProgress(event)
          break
        case 'stage_transition':
          store.setStageTransition(event)
          store.bumpRunsVersion()
          break
        case 'log_line':
          store.addLogLine(event)
          break
        case 'queue_update':
          store.setQueueUpdate(event)
          store.bumpRunsVersion()
          break
        case 'work_item_done':
          break
      }
    }

    connect()

    return () => {
      cancelled = true
      clearOfflineTimer()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      const ws = wsRef.current
      // close() on a CONNECTING socket logs a browser error, so let it open first.
      if (ws?.readyState === WebSocket.CONNECTING) ws.onopen = () => ws.close()
      else ws?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}
