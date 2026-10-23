import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useEngagements } from '../api/hooks';
import type { Engagement } from '../api/types';

interface EngagementContextValue {
  engagements: Engagement[];
  loading: boolean;
  selectedId: number | null;
  selected: Engagement | null;
  setSelectedId: (id: number | null) => void;
  reload: () => void;
}

const STORAGE_KEY = 'mudaletunnel.selectedEngagement';

const EngagementContext = createContext<EngagementContextValue | null>(null);

export function EngagementProvider({ children }: { children: ReactNode }) {
  const { items, loading, reload } = useEngagements();
  const [selectedId, setSelectedIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? Number(stored) : null;
  });

  useEffect(() => {
    if (items.length === 0) return;
    if (selectedId === null || !items.some((e) => e.id === selectedId)) {
      setSelectedIdState(items[0]?.id ?? null);
    }
  }, [items, selectedId]);

  const setSelectedId = (id: number | null) => {
    setSelectedIdState(id);
    if (id !== null) {
      localStorage.setItem(STORAGE_KEY, String(id));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const selected = useMemo(
    () => items.find((e) => e.id === selectedId) ?? null,
    [items, selectedId]
  );

  const value: EngagementContextValue = {
    engagements: items,
    loading,
    selectedId,
    selected,
    setSelectedId,
    reload,
  };

  return <EngagementContext.Provider value={value}>{children}</EngagementContext.Provider>;
}

export function useEngagementContext(): EngagementContextValue {
  const ctx = useContext(EngagementContext);
  if (!ctx) throw new Error('useEngagementContext must be used within EngagementProvider');
  return ctx;
}
