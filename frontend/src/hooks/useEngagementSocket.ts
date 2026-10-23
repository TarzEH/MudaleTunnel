import { useEffect, useRef, useState } from 'react';
import { getStoredApiKey, wsUrl } from '../api/client';
import type { WsMessage } from '../api/types';

export type ConnectionState = 'connecting' | 'open' | 'closed';

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const PING_INTERVAL_MS = 20000;

/**
 * Connects to the per-engagement WebSocket feed and dispatches incoming
 * messages to `onMessage`. Reconnects with exponential backoff (1s -> 30s cap).
 */
export function useEngagementSocket(
  engagementId: number | null,
  onMessage: (msg: WsMessage) => void
): ConnectionState {
  const [state, setState] = useState<ConnectionState>('closed');
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!engagementId) {
      setState('closed');
      return;
    }

    let socket: WebSocket | null = null;
    let closedByEffect = false;
    let backoff = MIN_BACKOFF_MS;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    function connect() {
      setState('connecting');
      let url = wsUrl(`/ws/v1/engagements/${engagementId}/`);
      const apiKey = getStoredApiKey();
      if (apiKey) {
        url += `?token=${encodeURIComponent(apiKey)}`;
      }
      socket = new WebSocket(url);

      socket.onopen = () => {
        backoff = MIN_BACKOFF_MS;
        setState('open');
        pingTimer = setInterval(() => {
          socket?.send(JSON.stringify({ type: 'ping' }));
        }, PING_INTERVAL_MS);
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(event.data) as WsMessage;
          onMessageRef.current(msg);
        } catch {
          // ignore malformed frames
        }
      };

      socket.onclose = () => {
        setState('closed');
        if (pingTimer) clearInterval(pingTimer);
        if (closedByEffect) return;
        reconnectTimer = setTimeout(() => {
          backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
          connect();
        }, backoff);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      closedByEffect = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      socket?.close();
    };
  }, [engagementId]);

  return state;
}
