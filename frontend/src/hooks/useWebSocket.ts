import { useEffect, useRef, useState } from 'react'
import { api, tokenStore } from '../api/client'
import type { WsEnvelope } from '../api/types'

// Stage 5 实时推送：取 ws-token 握手，断线自动重连，心跳每 30s。
export function useWebSocket(onEvent: (e: WsEnvelope) => void) {
  const [connected, setConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    let ws: WebSocket | null = null
    let heartbeat: ReturnType<typeof setInterval> | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let closed = false

    async function connect() {
      if (!tokenStore.get()) return
      let wsToken: string
      try {
        const { data } = await api.post('/auth/ws-token')
        wsToken = data.ws_token
      } catch {
        retry = setTimeout(connect, 5000)
        return
      }
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/review?token=${wsToken}`)

      ws.onopen = () => {
        setConnected(true)
        heartbeat = setInterval(() => ws?.readyState === WebSocket.OPEN && ws.send('HEARTBEAT'), 30000)
      }
      ws.onmessage = (ev) => {
        try {
          onEventRef.current(JSON.parse(ev.data) as WsEnvelope)
        } catch {
          /* 忽略非 JSON */
        }
      }
      ws.onclose = () => {
        setConnected(false)
        if (heartbeat) clearInterval(heartbeat)
        if (!closed) retry = setTimeout(connect, 3000)
      }
    }

    connect()
    return () => {
      closed = true
      if (heartbeat) clearInterval(heartbeat)
      if (retry) clearTimeout(retry)
      ws?.close()
    }
  }, [])

  return { connected }
}
