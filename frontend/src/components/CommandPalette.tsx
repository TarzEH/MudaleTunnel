import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTunnels } from '../api/hooks';
import { IconArrowRight, IconSearch } from './icons';

interface Command {
  id: string;
  label: string;
  hint?: string;
  onSelect: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const { items: tunnels } = useTunnels({});

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      const id = requestAnimationFrame(() => inputRef.current?.focus());
      return () => cancelAnimationFrame(id);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        onClose();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const staticCommands: Command[] = useMemo(
    () => [
      { id: 'nav-sessions', label: 'Go to Sessions', onSelect: () => navigate('/') },
      { id: 'nav-topology', label: 'Go to Topology', onSelect: () => navigate('/topology') },
      { id: 'nav-scans', label: 'Go to Scans', onSelect: () => navigate('/scans') },
      { id: 'nav-agents', label: 'Go to Agents', onSelect: () => navigate('/agents') },
      { id: 'nav-audit', label: 'Go to Audit', onSelect: () => navigate('/audit') },
      { id: 'nav-engagements', label: 'Go to Engagements', onSelect: () => navigate('/engagements') },
      { id: 'nav-settings', label: 'Go to Settings', onSelect: () => navigate('/settings') },
    ],
    [navigate]
  );

  const tunnelCommands: Command[] = useMemo(
    () =>
      tunnels.map((t) => ({
        id: `tunnel-${t.id}`,
        label: t.label,
        hint: t.kind_display,
        onSelect: () => navigate(`/tunnels/${t.id}`),
      })),
    [tunnels, navigate]
  );

  const allCommands = [...staticCommands, ...tunnelCommands];
  const filtered = query.trim()
    ? allCommands.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase()))
    : allCommands;

  function handleKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = filtered[activeIndex];
      if (cmd) {
        cmd.onSelect();
        onClose();
      }
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative z-10 w-full max-w-lg overflow-hidden rounded-lg border border-border-subtle bg-surface"
      >
        <div className="flex items-center gap-2 border-b border-border-subtle px-3">
          <IconSearch className="text-text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Jump to a screen or tunnel…"
            className="h-11 flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
            aria-label="Command palette search"
          />
        </div>
        <ul className="max-h-80 overflow-y-auto py-1" role="listbox">
          {filtered.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-text-muted">No matches</li>
          )}
          {filtered.map((cmd, idx) => (
            <li key={cmd.id} role="option" aria-selected={idx === activeIndex}>
              <button
                type="button"
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => {
                  cmd.onSelect();
                  onClose();
                }}
                className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                  idx === activeIndex ? 'bg-surface-2 text-text-primary' : 'text-text-secondary'
                }`}
              >
                <span className="flex items-center gap-2">
                  {cmd.label}
                  {cmd.hint && <span className="text-xs text-text-muted">{cmd.hint}</span>}
                </span>
                <IconArrowRight className="text-text-muted" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
