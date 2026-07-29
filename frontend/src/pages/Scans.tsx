import { useMemo, useState } from 'react';
import { useEngagementContext } from '../context/EngagementContext';
import { createScan, exposeService, useScanServices, useScans, useTunnels } from '../api/hooks';
import { ApiError } from '../api/client';
import type { Scan, ScanProfile, Service, Tunnel } from '../api/types';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Field, Select, TextInput } from '../components/Form';
import { IconChevronDown, IconChevronRight, IconRadar } from '../components/icons';
import { SkeletonRows } from '../components/Skeleton';
import { scanStatusTone, StatusDot } from '../components/StatusDot';
import { useSocketSubscription } from '../context/SocketContext';
import { formatAbsoluteTime, formatDuration, formatRelativeTime } from '../utils/time';

const PROFILE_OPTIONS: { value: ScanProfile; label: string }[] = [
  { value: 'discovery', label: 'Discovery (host sweep)' },
  { value: 'quick', label: 'Quick (top ports)' },
  { value: 'standard', label: 'Standard' },
  { value: 'full', label: 'Full (all ports)' },
  { value: 'udp_top', label: 'UDP top ports' },
];

export function Scans() {
  const { selected, selectedId } = useEngagementContext();
  const { items: scans, loading, error, reload } = useScans(selectedId);
  const { items: tunnels } = useTunnels({ engagement: selectedId });
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const [target, setTarget] = useState('');
  const [profile, setProfile] = useState<ScanProfile>('discovery');
  const [viaTunnel, setViaTunnel] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useSocketSubscription((msg) => {
    if (msg.type === 'scan.updated') reload();
  });

  const activeTunnels = useMemo(() => tunnels.filter((t) => t.status === 'active'), [tunnels]);

  const running = scans.filter((s) => s.status === 'queued' || s.status === 'running');
  const finished = scans.filter((s) => s.status !== 'queued' && s.status !== 'running');

  async function handleSubmit() {
    if (!selectedId) return;
    if (!target.trim()) {
      setFormError('Target is required (host, CIDR, or range).');
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await createScan({
        engagement: selectedId,
        target: target.trim(),
        profile,
        via_tunnel: viaTunnel ? Number(viaTunnel) : undefined,
      });
      setTarget('');
      reload();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : 'Failed to queue scan.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!selectedId) {
    return (
      <div className="p-8">
        <EmptyState icon={<IconRadar width={28} height={28} />} title="No engagement selected" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Scans</h1>
        <p className="text-sm text-text-secondary">Service discovery for {selected?.name ?? '—'}</p>
      </header>

      <div className="border-b border-border-subtle px-6 py-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Target" htmlFor="scan-target">
            <TextInput
              id="scan-target"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="10.10.0.0/24"
              mono
              className="w-56"
            />
          </Field>
          <Field label="Profile" htmlFor="scan-profile">
            <Select id="scan-profile" value={profile} onChange={(e) => setProfile(e.target.value as ScanProfile)}>
              {PROFILE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Via tunnel (optional)" htmlFor="scan-tunnel">
            <Select id="scan-tunnel" value={viaTunnel} onChange={(e) => setViaTunnel(e.target.value)}>
              <option value="">Direct</option>
              {activeTunnels.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Button variant="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Queuing…' : 'Run scan'}
          </Button>
        </div>
        {formError && <div className="mt-2 text-sm text-error">{formError}</div>}
      </div>

      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="mb-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error.message}
          </div>
        )}

        {running.length > 0 && (
          <div className="mb-6">
            <h2 className="mb-2 text-xs font-medium text-text-muted">Running</h2>
            <div className="flex flex-col gap-2">
              {running.map((scan) => (
                <div
                  key={scan.id}
                  className="flex items-center justify-between rounded-md border border-border-subtle px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <StatusDot tone={scanStatusTone(scan.status)} label={scan.status} />
                    <span className="font-mono text-sm text-text-primary">{scan.target}</span>
                    <Badge>{scan.profile_display}</Badge>
                  </div>
                  <span className="text-xs text-text-muted">
                    queued {formatRelativeTime(scan.queued_at)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <h2 className="mb-2 text-xs font-medium text-text-muted">History</h2>
        {!loading && finished.length === 0 && running.length === 0 ? (
          <EmptyState
            icon={<IconRadar width={28} height={28} />}
            title="No scans yet"
            description="Run a discovery or standard scan against an authorized target to enumerate services."
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="w-8 px-2 py-2"></th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Target</th>
                <th className="px-4 py-2 font-medium">Profile</th>
                <th className="px-4 py-2 font-medium">Hosts up</th>
                <th className="px-4 py-2 font-medium">Services</th>
                <th className="px-4 py-2 font-medium">Duration</th>
                <th className="px-4 py-2 font-medium">Finished</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={5} columns={8} />
              ) : (
                finished.map((scan) => (
                  <ScanRow
                    key={scan.id}
                    scan={scan}
                    expanded={expandedId === scan.id}
                    onToggle={() => setExpandedId(expandedId === scan.id ? null : scan.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function ScanRow({ scan, expanded, onToggle }: { scan: Scan; expanded: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="cursor-pointer border-b border-border-subtle hover:bg-surface" onClick={onToggle}>
        <td className="px-2 py-3 text-text-muted">
          {expanded ? <IconChevronDown /> : <IconChevronRight />}
        </td>
        <td className="px-4 py-3">
          <StatusDot tone={scanStatusTone(scan.status)} label={scan.status} />
        </td>
        <td className="px-4 py-3 font-mono text-text-primary">{scan.target}</td>
        <td className="px-4 py-3">
          <Badge>{scan.profile_display}</Badge>
        </td>
        <td className="px-4 py-3 text-text-secondary">{scan.hosts_up ?? '—'}</td>
        <td className="px-4 py-3 text-text-secondary">{scan.services_found ?? '—'}</td>
        <td className="px-4 py-3 font-mono text-text-secondary">{formatDuration(scan.duration_seconds)}</td>
        <td className="px-4 py-3 text-text-secondary">{formatAbsoluteTime(scan.finished_at)}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-border-subtle bg-surface">
          <td colSpan={8} className="px-4 py-3">
            {scan.error ? (
              <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
                {scan.error}
              </div>
            ) : (
              <ScanServices scanId={scan.id} viaTunnel={scan.via_tunnel} />
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function ScanServices({ scanId, viaTunnel }: { scanId: number; viaTunnel: number | null }) {
  const { items: services, loading } = useScanServices(scanId);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [results, setResults] = useState<
    Record<number, { ok: true; tunnel: Tunnel } | { ok: false; detail: string }>
  >({});

  const grouped = useMemo(() => {
    const map = new Map<string, Service[]>();
    for (const svc of services) {
      const list = map.get(svc.host) ?? [];
      list.push(svc);
      map.set(svc.host, list);
    }
    return Array.from(map.entries());
  }, [services]);

  async function handleExpose(svc: Service) {
    setBusyId(svc.id);
    try {
      const tunnel = await exposeService(svc.id);
      setResults((r) => ({ ...r, [svc.id]: { ok: true, tunnel } }));
    } catch (err) {
      setResults((r) => ({
        ...r,
        [svc.id]: { ok: false, detail: err instanceof ApiError ? err.detail : 'Failed to expose service.' },
      }));
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="text-sm text-text-muted">Loading services…</div>;
  if (grouped.length === 0) return <div className="text-sm text-text-muted">No services discovered.</div>;

  return (
    <div className="flex flex-col gap-4">
      {grouped.map(([host, svcs]) => (
        <div key={host}>
          <div className="mb-1.5 font-mono text-xs font-medium text-text-primary">
            {host} {svcs[0]?.hostname ? `(${svcs[0]?.hostname})` : ''}
          </div>
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr className="text-left text-text-muted">
                <th className="px-2 py-1 font-medium">Port</th>
                <th className="px-2 py-1 font-medium">State</th>
                <th className="px-2 py-1 font-medium">Service</th>
                <th className="px-2 py-1 font-medium">Product</th>
                <th className="px-2 py-1 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {svcs.map((svc) => {
                const result = results[svc.id];
                return (
                  <tr key={svc.id} className="border-t border-border-subtle">
                    <td className="px-2 py-1.5 font-mono text-text-primary">
                      {svc.port}/{svc.protocol}
                    </td>
                    <td className="px-2 py-1.5 text-text-secondary">{svc.state}</td>
                    <td className="px-2 py-1.5 text-text-secondary">{svc.service_name || '—'}</td>
                    <td className="px-2 py-1.5 text-text-secondary">
                      {svc.product} {svc.version}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      {viaTunnel && (
                        <div className="flex flex-col items-end gap-0.5">
                          <Button size="sm" onClick={() => handleExpose(svc)} disabled={busyId === svc.id}>
                            {busyId === svc.id ? 'Exposing…' : 'Expose'}
                          </Button>
                          {result && result.ok && (
                            <span className="font-mono text-[11px] text-ok">
                              127.0.0.1:{String(result.tunnel.spec?.local_port ?? '?')}
                            </span>
                          )}
                          {result && !result.ok && <span className="text-[11px] text-error">{result.detail}</span>}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
