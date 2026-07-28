import { createContext, useContext, useEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { useEngagementSocket } from '../hooks/useEngagementSocket';
import type { ConnectionState } from '../hooks/useEngagementSocket';
import { useEngagementContext } from './EngagementContext';
import type { WsMessage } from '../api/types';

type Listener = (msg: WsMessage) => void;

interface SocketContextValue {
  connectionState: ConnectionState;
  subscribe: (listener: Listener) => () => void;
}

const SocketContext = createContext<SocketContextValue | null>(null);

export function SocketProvider({ children }: { children: ReactNode }) {
  const { selectedId } = useEngagementContext();
  const listenersRef = useRef<Set<Listener>>(new Set());

  const handleMessage = (msg: WsMessage) => {
    listenersRef.current.forEach((listener) => listener(msg));
  };

  const connectionState = useEngagementSocket(selectedId, handleMessage);

  const value = useMemo<SocketContextValue>(
    () => ({
      connectionState,
      subscribe: (listener: Listener) => {
        listenersRef.current.add(listener);
        return () => listenersRef.current.delete(listener);
      },
    }),
    [connectionState]
  );

  return <SocketContext.Provider value={value}>{children}</SocketContext.Provider>;
}

export function useSocket(): SocketContextValue {
  const ctx = useContext(SocketContext);
  if (!ctx) throw new Error('useSocket must be used within SocketProvider');
  return ctx;
}

/** Subscribes to socket messages for the lifetime of the calling component. */
export function useSocketSubscription(listener: Listener) {
  const { subscribe } = useSocket();
  const listenerRef = useRef(listener);
  listenerRef.current = listener;

  useEffect(() => {
    return subscribe((msg) => listenerRef.current(msg));
  }, [subscribe]);
}
