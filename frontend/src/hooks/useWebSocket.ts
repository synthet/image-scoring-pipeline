import { useEffect, useRef } from 'react'
import { useWsStore } from '@/stores/wsStore'
import type { WsEvent } from '@/types/api'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/updates`
const RECONNECT_DELAY_MS = 2000

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const store = useWsStore()

  useEffect(() => {
    let cancelled = false

    function connect() {
      if (cancelled) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!cancelled) store.setConnected(true)
      }

      ws.onmessage = (ev) => {
        if (cancelled) return
        try {
          const event = JSON.parse(ev.data as string) as WsEvent
          dispatch(event)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        if (cancelled) return
        store.setConnected(false)
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    function dispatch(event: WsEvent) {
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
          // Do not bump runsVersion — fires per item and causes infinite update loops.
          // Live progress comes from run_progress; stage_transition/queue_update handle invalidation.
          break
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
}
