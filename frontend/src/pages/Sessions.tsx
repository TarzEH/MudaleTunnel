import { useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useEngagementContext } from '../context/EngagementContext';
import { useSocketSubscription } from '../context/SocketContext';
import { startTunnel, stopTunnel, useTunnels } from '../api/hooks';
import type { Tunnel, TunnelStatus } from '../api/types';
import { Badge } from '../components/Badge';
import { Button, IconButton } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { IconLogs, IconPlay, IconPlus, IconSearch, IconStop, IconTunnel } from '../components/icons';
import { Select, TextInput } from '../components/Form';
import { SkeletonRows } from '../components/Skeleton';
import { StatusDot, tunnelStatusTone } from '../components/StatusDot';
import { TunnelFormModal } from '../components/TunnelFormModal';
import type { TunnelPrefill } from '../components/TunnelFormModal';
import { formatDuration } from '../utils/time';

const STATUS_OPTIONS: Array<{ value: TunnelStatus | ''; label: string }> = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'starting', label: 'Starting' },
  { value: 'active', label: 'Active' },
  { value: 'degraded', label: 'Degraded' },
  { value: 'stopping', label: 'Stopping' },
  { value: 'stopped', label: 'Stopped' },
  { value: 'failed', label: 'Failed' },
];

export function Sessions() {
  const { selected, selectedId } = useEngagementContext();
  const navigate = useNavigate();
  const location = useLocation();
  const [statusFilter, setStatusFilter] = useState<TunnelStatus | ''>('');
  const [textFilter, setTextFilter] = useState('');
  const [modalOpen, setModalOpen] = useState(() =>
    Boolean((location.state as { prefill?: TunnelPrefill } | null)?.prefill)
  );
  const prefill = (location.state as { prefill?: TunnelPrefill } | null)?.prefill ?? null;

  const { items, loading, error, reload } = useTunnels({
    engagement: selectedId,
    status: statusFilter || null,
  });

  useSocketSubscription((msg) => {
    if (msg.type === 'tunnel.updated' || msg.type === 'agent.updated') {
      reload();
    }
  });

  const filtered = useMemo(() => {
    const needle = textFilter.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (t) =>
        t.label.toLowerCase().includes(needle) ||
        t.description.toLowerCase().includes(needle) ||
        (t.agent_name ?? '').toLowerCase().includes(needle)
    );
  }, [items, textFilter]);

  async function handleStop(tunnel: Tunnel) {
    await stopTunnel(tunnel.id);
    reload();
  }

  async function handleStart(tunnel: Tunnel) {
    await startTunnel(tunnel.id);
    reload();
  }

  if (!selectedId) {
    return (
      <div className="p-8">
        <EmptyState
          icon={<IconTunnel width={28} height={28} />}
          title="No engagement selected"
          description="Choose or create an engagement to view its tunnels."
          action={
            <Button variant="primary" onClick={() => navigate('/engagements')}>
              Go to engagements
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Sessions</h1>
          <p className="text-sm text-text-secondary">Active and historical tunnels for {selected?.name ?? '—'}</p>
        </div>
        <Button variant="primary" onClick={() => setModalOpen(true)}>
          <IconPlus /> New tunnel
        </Button>
      </header>

      <div className="flex items-center gap-3 border-b border-border-subtle px-6 py-3">
        <div className="relative w-64">
          <IconSearch className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <TextInput
            data-filter-focus
            value={textFilter}
            onChange={(e) => setTextFilter(e.target.value)}
            placeholder="Filter by label, description, agent…"
            className="w-full pl-8"
            aria-label="Filter tunnels"
          />
        </div>
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as TunnelStatus | '')}
          aria-label="Filter by status"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="mb-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error.message}
          </div>
        )}

        {!loading && filtered.length === 0 ? (
          <EmptyState
            icon={<IconTunnel width={28} height={28} />}
            title={items.length === 0 ? 'No tunnels yet' : 'No tunnels match your filters'}
            description={
              items.length === 0
                ? 'Create a tunnel to establish a pivot path into an authorized network segment.'
                : 'Try clearing the filter or status selection.'
            }
            action={
              items.length === 0 ? (
                <Button variant="primary" onClick={() => setModalOpen(true)}>
                  <IconPlus /> New tunnel
                </Button>
              ) : undefined
            }
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Label</th>
                <th className="px-4 py-2 font-medium">Kind</th>
                <th className="px-4 py-2 font-medium">Description</th>
                <th className="px-4 py-2 font-medium">Agent</th>
                <th className="px-4 py-2 font-medium">Uptime</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={6} columns={7} />
              ) : (
                filtered.map((tunnel) => (
                  <tr
                    key={tunnel.id}
                    className="group cursor-pointer border-b border-border-subtle hover:bg-surface"
                    onClick={() => navigate(`/tunnels/${tunnel.id}`)}
                  >
                    <td className="px-4 py-3">
                      <StatusDot tone={tunnelStatusTone(tunnel.status)} label={tunnel.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-text-primary">{tunnel.label}</td>
                    <td className="px-4 py-3">
                      <Badge>{tunnel.kind_display}</Badge>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 font-mono text-text-secondary">
                      {tunnel.description || '—'}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{tunnel.agent_name ?? '—'}</td>
                    <td className="px-4 py-3 font-mono text-text-secondary">
                      {formatDuration(tunnel.uptime_seconds)}
                    </td>
                    <td className="px-4 py-3">
                      <div
                        className="flex items-center justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {tunnel.desired_state === 'up' ? (
                          <IconButton aria-label={`Stop ${tunnel.label}`} onClick={() => handleStop(tunnel)}>
                            <IconStop />
                          </IconButton>
                        ) : (
                          <IconButton aria-label={`Start ${tunnel.label}`} onClick={() => handleStart(tunnel)}>
                            <IconPlay />
                          </IconButton>
                        )}
                        <IconButton
                          aria-label={`View logs for ${tunnel.label}`}
                          onClick={() => navigate(`/tunnels/${tunnel.id}`)}
                        >
                          <IconLogs />
                        </IconButton>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      {selectedId && (
        <TunnelFormModal
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          engagementId={selectedId}
          engagementName={selected?.name ?? ''}
          onCreated={reload}
          prefill={prefill}
        />
      )}
    </div>
  );
}
