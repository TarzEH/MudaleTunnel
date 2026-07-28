import { NavLink } from 'react-router-dom';
import { useEngagementContext } from '../context/EngagementContext';
import { useMe } from '../api/hooks';
import type { ConnectionState } from '../hooks/useEngagementSocket';
import { StatusDot } from './StatusDot';
import {
  IconBriefcase,
  IconChevronDown,
  IconLogs,
  IconMap,
  IconRadar,
  IconServer,
  IconSettings,
  IconShield,
  IconTunnel,
} from './icons';
import type { ReactNode } from 'react';

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Sessions', icon: <IconTunnel />, end: true },
  { to: '/topology', label: 'Topology', icon: <IconMap /> },
  { to: '/scans', label: 'Scans', icon: <IconRadar /> },
  { to: '/agents', label: 'Agents', icon: <IconServer /> },
  { to: '/audit', label: 'Audit', icon: <IconLogs /> },
  { to: '/engagements', label: 'Engagements', icon: <IconBriefcase /> },
  { to: '/settings', label: 'Settings', icon: <IconSettings /> },
];

function connectionTone(state: ConnectionState): 'ok' | 'warn' | 'neutral' {
  if (state === 'open') return 'ok';
  if (state === 'connecting') return 'warn';
  return 'neutral';
}

function connectionLabel(state: ConnectionState): string {
  if (state === 'open') return 'Live';
  if (state === 'connecting') return 'Connecting';
  return 'Offline';
}

export function Sidebar({ connectionState }: { connectionState: ConnectionState }) {
  const { engagements, selectedId, setSelectedId, loading } = useEngagementContext();
  const { data: me } = useMe();

  return (
    <aside className="flex h-full w-[220px] shrink-0 flex-col border-r border-border-subtle bg-surface max-md:w-14">
      <div className="flex h-14 items-center border-b border-border-subtle px-4 max-md:justify-center max-md:px-0">
        <span className="text-sm font-semibold tracking-tight text-text-primary max-md:hidden">
          MudaleTunnel
        </span>
        <span className="hidden text-sm font-semibold text-text-primary max-md:inline">MT</span>
      </div>

      <div className="border-b border-border-subtle p-3 max-md:hidden">
        <label htmlFor="engagement-select" className="mb-1 block text-xs font-medium text-text-muted">
          Engagement
        </label>
        <div className="relative">
          <select
            id="engagement-select"
            value={selectedId ?? ''}
            onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : null)}
            disabled={loading || engagements.length === 0}
            className="h-8 w-full appearance-none rounded-md border border-border-subtle bg-base pl-2.5 pr-7 text-xs text-text-primary focus-visible:border-accent disabled:opacity-50"
          >
            {engagements.length === 0 && <option value="">No engagements</option>}
            {engagements.map((eng) => (
              <option key={eng.id} value={eng.id}>
                {eng.name}
              </option>
            ))}
          </select>
          <IconChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-text-muted" />
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-2" aria-label="Primary">
        <ul className="flex flex-col gap-0.5 px-2">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors max-md:justify-center max-md:px-0 ${
                    isActive
                      ? 'bg-surface-2 text-text-primary'
                      : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary'
                  }`}
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute left-0 top-1 bottom-1 w-0.5 rounded-full bg-accent max-md:hidden" />
                    )}
                    <span className="shrink-0">{item.icon}</span>
                    <span className="max-md:hidden">{item.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="border-t border-border-subtle p-3 max-md:flex max-md:justify-center max-md:p-2">
        <div className="flex items-center gap-2 max-md:flex-col">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-2 text-xs font-medium text-text-primary">
            <IconShield width={14} height={14} />
          </div>
          <div className="min-w-0 flex-1 max-md:hidden">
            <div className="truncate text-xs font-medium text-text-primary">
              {me?.callsign || me?.username || 'Unknown operator'}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] uppercase tracking-wide text-text-muted">
                {me?.role ?? '—'}
              </span>
            </div>
          </div>
        </div>
        <div className="mt-2 max-md:hidden">
          <StatusDot tone={connectionTone(connectionState)} label={connectionLabel(connectionState)} />
        </div>
      </div>
    </aside>
  );
}
