import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import type { Me } from '../api/types';

interface AuthValue {
  me: Me | null;
  loading: boolean;
  setMe: (me: Me | null) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

/**
 * Resolves the current operator once at startup.
 *
 * Everything below this boundary can assume it is authenticated, so no page
 * needs to handle a null user — and nothing about the deployment renders before
 * the server has confirmed who is asking.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Me>('/me/')
      .then((value) => {
        if (!cancelled) setMe(value);
      })
      .catch((err) => {
        // 401/403 simply means "not signed in"; anything else is still a
        // reason to show the sign-in screen rather than a broken shell.
        if (!cancelled && !(err instanceof ApiError)) {
          console.error('Failed to resolve the current operator', err);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.post('/auth/logout/');
    } finally {
      setMe(null);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ me, loading, setMe, signOut }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
