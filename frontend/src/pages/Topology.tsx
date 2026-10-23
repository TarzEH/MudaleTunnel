import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useEngagementContext } from '../context/EngagementContext';
import { exposeService, usePivotMap, useServices, useTunnels } from '../api/hooks';
import { ApiError } from '../api/client';
import type { PivotEntry, ReachableHost, Service, Tunnel } from '../api/types';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { IconMap } from '../components/icons';
import { StatusDot, tunnelStatusTone } from '../components/StatusDot';

const STATUS_COLOR: Record<string, string> = {
  ok: 'var(--status-ok)',
  warn: 'var(--status-warn)',
  error: 'var(--status-error)',
  info: 'var(--status-info)',
  neutral: 'var(--border-strong)',
};

const NODE_W = 176;
const NODE_H = 40;
const COL_GAP = 240;
const ROW_GAP = 56;

type SelectedNode =
  | { kind: 'operator' }
  | { kind: 'pivot'; pivot: PivotEntry }
  | { kind: 'host'; host: ReachableHost; pivot: PivotEntry | null };

export function Topology() {
  const { selected, selectedId } = useEngagementContext();
  const navigate = useNavigate();
  const { data: map, loading: mapLoading, error: mapError } = usePivotMap(selectedId);
  const { items: tunnels } = useTunnels({ engagement: selectedId });
  const { items: services } = useServices(selectedId);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);

  const tunnelsById = useMemo(() => {
    const m = new Map<number, Tunnel>();
    for (const t of tunnels) m.set(t.id, t);
    return m;
  }, [tunnels]);

  const directHosts = map?.direct ?? [];
  const pivots = map?.pivots ?? [];

  const layoutRowCount = Math.max(
    directHosts.length + pivots.reduce((acc, p) => acc + Math.max(p.hosts.length, 1), 0),
    1
  );

  const height = Math.max(NODE_H + 40, layoutRowCount * ROW_GAP + 40, pivots.length * ROW_GAP + 40);
  const width = NODE_W * 3 + COL_GAP * 2 + 40;
  const operatorPos = { x: 20, y: height / 2 - NODE_H / 2 };

  const { hostPositions, pivotPositions } = useMemo(() => {
    const hostPos = new Map<ReachableHost, { x: number; y: number }>();
    const pivotPos = new Map<number, { x: number; y: number }>();
    const denom = layoutRowCount + 1;
    const rowY = (idx: number) => (height / denom) * (idx + 1) - NODE_H / 2;

    directHosts.forEach((host, i) => {
      hostPos.set(host, { x: 20 + COL_GAP * 2, y: rowY(i) });
    });

    let cursor = directHosts.length;
    for (const pivot of pivots) {
      const count = Math.max(pivot.hosts.length, 1);
      const mid = cursor + (count - 1) / 2;
      pivotPos.set(pivot.tunnel, { x: 20 + COL_GAP, y: rowY(mid) });
      pivot.hosts.forEach((host, j) => {
        hostPos.set(host, { x: 20 + COL_GAP * 2, y: rowY(cursor + j) });
      });
      cursor += count;
    }

    return { hostPositions: hostPos, pivotPositions: pivotPos };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directHosts, pivots, layoutRowCount, height]);

  if (!selectedId) {
    return (
      <div className="p-8">
        <EmptyState icon={<IconMap width={28} height={28} />} title="No engagement selected" />
      </div>
    );
  }

  const isEmpty = !mapLoading && !mapError && (!map || map.total_hosts === 0);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Topology</h1>
        <p className="text-sm text-text-secondary">
          Proven reachability for {selected?.name ?? '—'}
          {map && !isEmpty && (
            <>
              {' '}
              — {map.total_hosts} host{map.total_hosts === 1 ? '' : 's'} across {pivots.length} pivot
              {pivots.length === 1 ? '' : 's'}
            </>
          )}
        </p>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-auto p-6">
          {mapError && (
            <div className="mb-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
              {mapError.message}
            </div>
          )}

          {mapLoading ? (
            <div className="text-sm text-text-muted">Loading topology…</div>
          ) : isEmpty ? (
            <EmptyState
              icon={<IconMap width={28} height={28} />}
              title="No reachable hosts yet"
              description="This map is built from evidence, not assumption. Open a SOCKS pivot (an SSH dynamic tunnel) and run an nmap scan through it — what nmap actually finds is what shows up here."
              action={
                <button className="text-sm text-accent underline" onClick={() => navigate('/scans')}>
                  Go run a scan
                </button>
              }
            />
          ) : (
            <svg width={width} height={height} role="img" aria-label="Pivot topology graph">
              {/* Edges: operator -> direct host (solid) */}
              {directHosts.map((host, idx) => {
                const pos = hostPositions.get(host);
                if (!pos) return null;
                return (
                  <line
                    key={`direct-${idx}`}
                    x1={operatorPos.x + NODE_W}
                    y1={operatorPos.y + NODE_H / 2}
                    x2={pos.x}
                    y2={pos.y + NODE_H / 2}
                    stroke={STATUS_COLOR.neutral}
                    strokeWidth={1.5}
                  />
                );
              })}

              {/* Edges: operator -> pivot (dashed, labeled with opened subnets) */}
              {pivots.map((pivot) => {
                const pos = pivotPositions.get(pivot.tunnel);
                if (!pos) return null;
                const tunnel = tunnelsById.get(pivot.tunnel);
                const color = tunnel ? STATUS_COLOR[tunnelStatusTone(tunnel.status)] : STATUS_COLOR.neutral;
                const midX = (operatorPos.x + NODE_W + pos.x) / 2;
                const midY = (operatorPos.y + NODE_H / 2 + pos.y + NODE_H / 2) / 2;
                return (
                  <g key={`op-pivot-${pivot.tunnel}`}>
                    <line
                      x1={operatorPos.x + NODE_W}
                      y1={operatorPos.y + NODE_H / 2}
                      x2={pos.x}
                      y2={pos.y + NODE_H / 2}
                      stroke={color}
                      strokeWidth={1.5}
                      strokeDasharray="5 4"
                    />
                    <text
                      x={midX}
                      y={midY - 6}
                      textAnchor="middle"
                      fontSize={9}
                      className="font-mono"
                      fill="var(--text-muted)"
                    >
                      {pivot.subnets.join(', ') || 'no subnets yet'}
                    </text>
                  </g>
                );
              })}

              {/* Edges: pivot -> its hosts (dashed) */}
              {pivots.map((pivot) => {
                const pivotPos = pivotPositions.get(pivot.tunnel);
                if (!pivotPos) return null;
                const tunnel = tunnelsById.get(pivot.tunnel);
                const color = tunnel ? STATUS_COLOR[tunnelStatusTone(tunnel.status)] : STATUS_COLOR.neutral;
                return pivot.hosts.map((host, idx) => {
                  const pos = hostPositions.get(host);
                  if (!pos) return null;
                  return (
                    <line
                      key={`pivot-${pivot.tunnel}-host-${idx}`}
                      x1={pivotPos.x + NODE_W}
                      y1={pivotPos.y + NODE_H / 2}
                      x2={pos.x}
                      y2={pos.y + NODE_H / 2}
                      stroke={color}
                      strokeWidth={1.5}
                      strokeDasharray="5 4"
                    />
                  );
                });
              })}

              {/* Operator node */}
              <g
                transform={`translate(${operatorPos.x}, ${operatorPos.y})`}
                onClick={() => setSelectedNode({ kind: 'operator' })}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedNode({ kind: 'operator' }); } }}
                tabIndex={0}
                role="button"
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
                  Operator
                </text>
              </g>

              {/* Pivot nodes */}
              {pivots.map((pivot) => {
                const pos = pivotPositions.get(pivot.tunnel);
                if (!pos) return null;
                const tunnel = tunnelsById.get(pivot.tunnel);
                const color = tunnel ? STATUS_COLOR[tunnelStatusTone(tunnel.status)] : STATUS_COLOR.neutral;
                return (
                  <g
                    key={pivot.tunnel}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => setSelectedNode({ kind: 'pivot', pivot })}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedNode({ kind: 'pivot', pivot }); } }}
                    tabIndex={0}
                    role="button"
                    className="cursor-pointer"
                  >
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill="var(--bg-surface)"
                      stroke={color}
                      strokeWidth={
                        selectedNode?.kind === 'pivot' && selectedNode.pivot.tunnel === pivot.tunnel ? 2 : 1
                      }
                    />
                    <text x={10} y={16} fontSize={11} fill="var(--text-primary)" className="font-mono">
                      {pivot.label}
                    </text>
                    <text x={10} y={30} fontSize={10} fill="var(--text-muted)">
                      {pivot.hosts.length} host{pivot.hosts.length === 1 ? '' : 's'}
                    </text>
                  </g>
                );
              })}

              {/* Host nodes */}
              {[...directHosts, ...pivots.flatMap((p) => p.hosts)].map((host, idx) => {
                const pos = hostPositions.get(host);
                if (!pos) return null;
                const ownerPivot = pivots.find((p) => p.hosts.includes(host)) ?? null;
                const isSelected = selectedNode?.kind === 'host' && selectedNode.host === host;
                return (
                  <g
                    key={`host-${idx}`}
                    transform={`translate(${pos.x}, ${pos.y})`}
                    onClick={() => setSelectedNode({ kind: 'host', host, pivot: ownerPivot })}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedNode({ kind: 'host', host, pivot: ownerPivot }); } }}
                    tabIndex={0}
                    role="button"
                    className="cursor-pointer"
                  >
                    <rect
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill="var(--bg-surface)"
                      stroke="var(--border-subtle)"
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    <text x={10} y={16} fontSize={11} className="font-mono" fill="var(--text-primary)">
                      {host.host}
                    </text>
                    <text x={10} y={30} fontSize={10} fill="var(--text-muted)">
                      {host.hostname || `${host.open_ports.length} port${host.open_ports.length === 1 ? '' : 's'}`}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}
        </div>

        {selectedNode && (
          <aside className="w-80 shrink-0 overflow-y-auto border-l border-border-subtle p-4">
            <NodeDetails
              node={selectedNode}
              tunnelsById={tunnelsById}
              services={services}
              onClose={() => setSelectedNode(null)}
            />
          </aside>
        )}
      </div>
    </div>
  );
}

function NodeDetails({
  node,
  tunnelsById,
  services,
  onClose,
}: {
  node: SelectedNode;
  tunnelsById: Map<number, Tunnel>;
  services: Service[];
  onClose: () => void;
}) {
  const navigate = useNavigate();
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-primary">
          {node.kind === 'operator' ? 'Operator' : node.kind === 'pivot' ? 'Pivot' : 'Host'}
        </h2>
        <button onClick={onClose} className="text-xs text-text-muted hover:text-text-primary">
          Close
        </button>
      </div>

      {node.kind === 'operator' && (
        <p className="text-sm text-text-secondary">
          The operator workstation. Hosts connected directly were reached without going through a pivot.
        </p>
      )}

      {node.kind === 'pivot' && (
        <PivotDetails pivot={node.pivot} tunnel={tunnelsById.get(node.pivot.tunnel) ?? null} onNavigate={navigate} />
      )}

      {node.kind === 'host' && <HostPanel host={node.host} pivot={node.pivot} services={services} />}
    </div>
  );
}

function PivotDetails({
  pivot,
  tunnel,
  onNavigate,
}: {
  pivot: PivotEntry;
  tunnel: Tunnel | null;
  onNavigate: (path: string) => void;
}) {
  return (
    <dl className="flex flex-col gap-3 text-sm">
      <Row label="Label" value={pivot.label} mono />
      {tunnel && (
        <Row label="Status" value={<StatusDot tone={tunnelStatusTone(tunnel.status)} label={tunnel.status} />} />
      )}
      <div>
        <dt className="mb-1.5 text-text-secondary">Subnets opened</dt>
        <dd className="flex flex-wrap gap-1">
          {pivot.subnets.length === 0 && <span className="text-text-muted">none yet</span>}
          {pivot.subnets.map((cidr) => (
            <Badge key={cidr} mono>
              {cidr}
            </Badge>
          ))}
        </dd>
      </div>
      <Row label="Hosts found" value={String(pivot.hosts.length)} />
      <Button size="sm" onClick={() => onNavigate(`/tunnels/${pivot.tunnel}`)}>
        View tunnel
      </Button>
    </dl>
  );
}

function HostPanel({
  host,
  pivot,
  services,
}: {
  host: ReachableHost;
  pivot: PivotEntry | null;
  services: Service[];
}) {
  const navigate = useNavigate();
  const [busyPort, setBusyPort] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<
    Record<number, { ok: true; tunnel: Tunnel } | { ok: false; detail: string }>
  >({});

  async function handleExpose(port: number) {
    const svc = services.find((s) => s.host === host.host && s.port === port);
    if (!svc) {
      setFeedback((f) => ({
        ...f,
        [port]: { ok: false, detail: 'No matching discovered service. Run a scan through this pivot first.' },
      }));
      return;
    }
    setBusyPort(port);
    try {
      const created = await exposeService(svc.id, {});
      setFeedback((f) => ({ ...f, [port]: { ok: true, tunnel: created } }));
    } catch (err) {
      setFeedback((f) => ({
        ...f,
        [port]: { ok: false, detail: err instanceof ApiError ? err.detail : 'Failed to expose service.' },
      }));
    } finally {
      setBusyPort(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="font-mono text-sm text-text-primary">{host.host}</div>
      {host.hostname && <div className="text-xs text-text-muted">{host.hostname}</div>}
      <div className="text-xs text-text-muted">
        {pivot ? (
          <>
            Reached through <span className="font-mono text-text-secondary">{pivot.label}</span>
          </>
        ) : (
          'Reached directly, no pivot.'
        )}
      </div>

      <ul className="flex flex-col gap-1.5">
        {host.open_ports.length === 0 && <li className="text-sm text-text-muted">No open ports recorded.</li>}
        {host.open_ports.map((port) => {
          const fb = feedback[port];
          return (
            <li key={port} className="rounded-md border border-border-subtle px-2.5 py-1.5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-text-primary">{port}</span>
                <Button size="sm" onClick={() => handleExpose(port)} disabled={busyPort === port}>
                  {busyPort === port ? 'Exposing…' : 'Expose'}
                </Button>
              </div>
              {fb && fb.ok && (
                <div className="mt-1.5 text-xs text-ok">
                  Exposed on local port{' '}
                  <span className="font-mono">{String(fb.tunnel.spec?.local_port ?? '?')}</span> —{' '}
                  <button className="underline" onClick={() => navigate(`/tunnels/${fb.tunnel.id}`)}>
                    view tunnel
                  </button>
                </div>
              )}
              {fb && !fb.ok && <div className="mt-1.5 text-xs text-error">{fb.detail}</div>}
            </li>
          );
        })}
      </ul>
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
