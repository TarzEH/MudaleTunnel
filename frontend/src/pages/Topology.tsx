import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useEngagementContext } from '../context/EngagementContext';
import { useAgents, useMe, useTunnels } from '../api/hooks';
import type { Agent, Tunnel, TunnelKind } from '../api/types';
import { EmptyState } from '../components/EmptyState';
import { IconMap } from '../components/icons';
import { agentStatusTone, StatusDot, tunnelStatusTone } from '../components/StatusDot';
import { Badge } from '../components/Badge';
import { formatRelativeTime } from '../utils/time';

const STATUS_COLOR: Record<string, string> = {
  ok: 'var(--status-ok)',
  warn: 'var(--status-warn)',
  error: 'var(--status-error)',
  info: 'var(--status-info)',
  neutral: 'var(--border-strong)',
};

function edgeDashArray(kind: TunnelKind): string | undefined {
  if (kind === 'ssh_dynamic') return '5 4';
  if (kind === 'ssh_remote' || kind === 'ssh_remote_dynamic') return '1.5 3.5';
  return undefined;
}

interface CidrEdge {
  cidr: string;
  agentId: number;
  tunnel: Tunnel;
}

type SelectedNode =
  | { kind: 'operator' }
  | { kind: 'agent'; agent: Agent }
  | { kind: 'cidr'; cidr: string; tunnels: Tunnel[] };

const NODE_W = 168;
const NODE_H = 40;
const COL_GAP = 220;
const ROW_GAP = 64;

export function Topology() {
  const { selected, selectedId } = useEngagementContext();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { items: agents, loading: agentsLoading } = useAgents(selectedId);
  const { items: tunnels, loading: tunnelsLoading } = useTunnels({ engagement: selectedId });
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);

  const cidrEdges: CidrEdge[] = useMemo(() => {
    const edges: CidrEdge[] = [];
    for (const t of tunnels) {
      if (!t.agent) continue;
      for (const route of t.routes) {
        edges.push({ cidr: route.cidr, agentId: t.agent, tunnel: t });
      }
    }
    return edges;
  }, [tunnels]);

  const cidrList = useMemo(() => {
    const set = new Map<string, Tunnel[]>();
    for (const edge of cidrEdges) {
      const list = set.get(edge.cidr) ?? [];
      list.push(edge.tunnel);
      set.set(edge.cidr, list);
    }
    return Array.from(set.entries()).map(([cidr, ts]) => ({ cidr, tunnels: ts }));
  }, [cidrEdges]);

  const agentsWithTunnels = useMemo(
    () => agents.filter((a) => tunnels.some((t) => t.agent === a.id)),
    [agents, tunnels]
  );
  const displayAgents = agentsWithTunnels.length > 0 ? agentsWithTunnels : agents;

  const height = Math.max(
    NODE_H + 40,
    Math.max(displayAgents.length, 1) * ROW_GAP + 40,
    cidrList.length * ROW_GAP + 40
  );
  const width = NODE_W * 3 + COL_GAP * 2 + 40;

  const operatorPos = { x: 20, y: height / 2 - NODE_H / 2 };
  const agentPositions = new Map<number, { x: number; y: number }>();
  displayAgents.forEach((agent, idx) => {
    const y = (height / (displayAgents.length + 1)) * (idx + 1) - NODE_H / 2;
    agentPositions.set(agent.id, { x: 20 + COL_GAP, y });
  });
  const cidrPositions = new Map<string, { x: number; y: number }>();
  cidrList.forEach((entry, idx) => {
    const y = (height / (cidrList.length + 1)) * (idx + 1) - NODE_H / 2;
    cidrPositions.set(entry.cidr, { x: 20 + COL_GAP * 2, y });
  });

  if (!selectedId) {
    return (
      <div className="p-8">
        <EmptyState icon={<IconMap width={28} height={28} />} title="No engagement selected" />
      </div>
    );
  }

  const loading = agentsLoading || tunnelsLoading;

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Topology</h1>
        <p className="text-sm text-text-secondary">Pivot path for {selected?.name ?? '—'}</p>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div className="text-sm text-text-muted">Loading topology…</div>
          ) : displayAgents.length === 0 ? (
            <EmptyState
              icon={<IconMap width={28} height={28} />}
              title="No pivot paths yet"
              description="Once tunnels are established through agents, the operator-to-network graph appears here."
              action={
                <button className="text-sm text-accent underline" onClick={() => navigate('/')}>
                  Create a tunnel
                </button>
              }
            />
          ) : (
            <svg width={width} height={height} role="img" aria-label="Network topology graph">
              {/* Edges: operator -> agent */}
              {displayAgents.map((agent) => {
                const tunnel = tunnels.find((t) => t.agent === agent.id);
                if (!tunnel) return null;
                const pos = agentPositions.get(agent.id);
                if (!pos) return null;
                const color = STATUS_COLOR[tunnelStatusTone(tunnel.status)];
                return (
                  <line
                    key={`op-${agent.id}`}
                    x1={operatorPos.x + NODE_W}
                    y1={operatorPos.y + NODE_H / 2}
                    x2={pos.x}
                    y2={pos.y + NODE_H / 2}
                    stroke={color}
                    strokeWidth={1.5}
                    strokeDasharray={edgeDashArray(tunnel.kind)}
                  />
                );
              })}

              {/* Edges: agent -> cidr */}
              {cidrEdges.map((edge, idx) => {
                const agentPos = agentPositions.get(edge.agentId);
                const cidrPos = cidrPositions.get(edge.cidr);
                if (!agentPos || !cidrPos) return null;
                const color = STATUS_COLOR[tunnelStatusTone(edge.tunnel.status)];
                return (
                  <line
                    key={`route-${idx}`}
                    x1={agentPos.x + NODE_W}
                    y1={agentPos.y + NODE_H / 2}
                    x2={cidrPos.x}
                    y2={cidrPos.y + NODE_H / 2}
                    stroke={color}
                    strokeWidth={1.5}
                    strokeDasharray={edgeDashArray(edge.tunnel.kind)}
                  />
                );
              })}

              {/* Operator node */}
              <g
                transform={`translate(${operatorPos.x}, ${operatorPos.y})`}
                onClick={() => setSelectedNode({ kind: 'operator' })}
                className="cursor-pointer"
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx={6}
                  fill="var(--bg-surface)"
                  stroke="var(--border-strong)"
                  strokeWidth={selectedNode?.kind === 'operator' ? 2 : 1}
                />
                <text x={NODE_W / 2} y={NODE_H / 2 + 4} textAnchor="middle" fontSize={12} fill="var(--text-primary)">
                  {me?.callsign || me?.username || 'Operator'}
                </text>
              </g>

              {/* Agent nodes */}
              {displayAgents.map((agent) => {
                const pos = agentPositions.get(agent.id);
                if (!pos) return null;
                return (
                  <g
                    key={agent.id}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => setSelectedNode({ kind: 'agent', agent })}
                    className="cursor-pointer"
                  >
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill="var(--bg-surface)"
                      stroke={STATUS_COLOR[agentStatusTone(agent.status)]}
                      strokeWidth={
                        selectedNode?.kind === 'agent' && selectedNode.agent.id === agent.id ? 2 : 1
                      }
                    />
                    <text x={10} y={16} fontSize={11} fill="var(--text-primary)" className="font-mono">
                      {agent.name}
                    </text>
                    <text x={10} y={30} fontSize={10} fill="var(--text-muted)">
                      {agent.status}
                    </text>
                  </g>
                );
              })}

              {/* CIDR nodes */}
              {cidrList.map((entry) => {
                const pos = cidrPositions.get(entry.cidr);
                if (!pos) return null;
                return (
                  <g
                    key={entry.cidr}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => setSelectedNode({ kind: 'cidr', cidr: entry.cidr, tunnels: entry.tunnels })}
                    className="cursor-pointer"
                  >
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill="var(--bg-surface)"
                      stroke="var(--border-subtle)"
                      strokeWidth={
                        selectedNode?.kind === 'cidr' && selectedNode.cidr === entry.cidr ? 2 : 1
                      }
                    />
                    <text
                      x={NODE_W / 2}
                      y={NODE_H / 2 + 4}
                      textAnchor="middle"
                      fontSize={12}
                      className="font-mono"
                      fill="var(--text-primary)"
                    >
                      {entry.cidr}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        {selectedNode && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-border-subtle p-4">
            <NodeDetails node={selectedNode} onClose={() => setSelectedNode(null)} />
          </aside>
        )}
      </div>
    </div>
  );
}

function NodeDetails({ node, onClose }: { node: SelectedNode; onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-primary">
          {node.kind === 'operator' ? 'Operator' : node.kind === 'agent' ? 'Agent' : 'Routed CIDR'}
        </h2>
        <button onClick={onClose} className="text-xs text-text-muted hover:text-text-primary">
          Close
        </button>
      </div>

      {node.kind === 'operator' && (
        <p className="text-sm text-text-secondary">
          The operator workstation initiating tunnels into this engagement.
        </p>
      )}

      {node.kind === 'agent' && (
        <dl className="flex flex-col gap-2 text-sm">
          <Row label="Name" value={node.agent.name} mono />
          <Row
            label="Status"
            value={<StatusDot tone={agentStatusTone(node.agent.status)} label={node.agent.status} />}
          />
          <Row label="Engine" value={<Badge>{node.agent.engine}</Badge>} />
          <Row label="Host" value={`${node.agent.remote_host}:${node.agent.remote_port}`} mono />
          <Row label="OS" value={node.agent.operating_system || '—'} />
          <Row label="Last seen" value={formatRelativeTime(node.agent.last_seen_at)} />
        </dl>
      )}

      {node.kind === 'cidr' && (
        <div className="flex flex-col gap-3">
          <div className="font-mono text-sm text-text-primary">{node.cidr}</div>
          <div className="text-xs text-text-muted">Reachable via {node.tunnels.length} tunnel(s)</div>
          <ul className="flex flex-col gap-1.5">
            {node.tunnels.map((t) => (
              <li key={t.id}>
                <button
                  onClick={() => navigate(`/tunnels/${t.id}`)}
                  className="flex w-full items-center justify-between rounded-md border border-border-subtle px-2.5 py-1.5 text-left hover:bg-surface-2"
                >
                  <span className="font-mono text-xs text-text-primary">{t.label}</span>
                  <StatusDot tone={tunnelStatusTone(t.status)} label={t.status} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-text-secondary">{label}</dt>
      <dd className={mono ? 'font-mono text-text-primary' : 'text-text-primary'}>{value}</dd>
    </div>
  );
}
