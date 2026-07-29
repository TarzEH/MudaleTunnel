import { useEngagementContext } from '../context/EngagementContext';
import { useSocketSubscription } from '../context/SocketContext';
import { useAgents } from '../api/hooks';
import { Badge } from '../components/Badge';
import { EmptyState } from '../components/EmptyState';
import { IconServer } from '../components/icons';
import { SkeletonRows } from '../components/Skeleton';
import { agentStatusTone, StatusDot } from '../components/StatusDot';
import { formatRelativeTime } from '../utils/time';

export function Agents() {
  const { selected, selectedId } = useEngagementContext();
  const { items: agents, loading, error, reload } = useAgents(selectedId);

  useSocketSubscription((msg) => {
    if (msg.type === 'agent.updated') reload();
  });

  if (!selectedId) {
    return (
      <div className="p-8">
        <EmptyState icon={<IconServer width={28} height={28} />} title="No engagement selected" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Agents</h1>
        <p className="text-sm text-text-secondary">Pivot points registered for {selected?.name ?? '—'}</p>
      </header>

      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="mb-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error.message}
          </div>
        )}

        {!loading && agents.length === 0 ? (
          <EmptyState
            icon={<IconServer width={28} height={28} />}
            title="No agents registered"
            description="Agents are SSH footholds you register — point the engine at a reachable host and it checks in here."
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Engine</th>
                <th className="px-4 py-2 font-medium">Host</th>
                <th className="px-4 py-2 font-medium">OS / Arch</th>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Reachable CIDRs</th>
                <th className="px-4 py-2 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} columns={8} />
              ) : (
                agents.map((agent) => (
                  <tr key={agent.id} className="border-b border-border-subtle hover:bg-surface">
                    <td className="px-4 py-3">
                      <StatusDot tone={agentStatusTone(agent.status)} label={agent.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-text-primary">
                      {agent.name}
                      {agent.is_privileged && (
                        <Badge tone="warn" className="ml-2">
                          priv
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge>{agent.engine}</Badge>
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary">
                      {agent.remote_host}:{agent.remote_port}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {agent.operating_system || '—'} {agent.architecture && `/ ${agent.architecture}`}
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{agent.remote_username || '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {agent.reachable_cidrs.length === 0 && (
                          <span className="text-text-muted">—</span>
                        )}
                        {agent.reachable_cidrs.map((cidr) => (
                          <Badge key={cidr} mono>
                            {cidr}
                          </Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{formatRelativeTime(agent.last_seen_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
