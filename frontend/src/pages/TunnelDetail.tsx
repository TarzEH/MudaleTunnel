import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  autoExpose,
  fetchTunnelLogs,
  getProxychains,
  getReachable,
  startTunnel,
  stopTunnel,
  useTunnel,
} from '../api/hooks';
import { ApiError } from '../api/client';
import { useSocketSubscription } from '../context/SocketContext';
import type { LogLevel, ReachableResponse, TunnelLog } from '../api/types';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { IconArrowRight, IconPlay, IconStop } from '../components/icons';
import { SkeletonBlock } from '../components/Skeleton';
import { StatusDot, tunnelStatusTone } from '../components/StatusDot';
import { formatAbsoluteTime, formatDuration } from '../utils/time';

const LEVEL_COLOR: Record<string, string> = {
  debug: 'var(--text-muted)',
  info: 'var(--status-info)',
  warning: 'var(--status-warn)',
  error: 'var(--status-error)',
  critical: 'var(--status-error)',
};

function levelColor(level: string): string {
  return LEVEL_COLOR[level] ?? 'var(--text-secondary)';
}

const SCROLL_BOTTOM_THRESHOLD = 48;

export function TunnelDetail() {
  const params = useParams<{ id: string }>();
  const tunnelId = params.id ? Number(params.id) : null;
  const navigate = useNavigate();
  const { data: tunnel, loading, reload, setState } = useTunnel(tunnelId);

  const [logs, setLogs] = useState<TunnelLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!tunnelId) return;
    setLogsLoading(true);
    fetchTunnelLogs(tunnelId)
      .then((res) => setLogs(res.results.slice().reverse()))
      .finally(() => setLogsLoading(false));
  }, [tunnelId]);

  useSocketSubscription(
    useCallback(
      (msg) => {
        if (!tunnelId) return;
        if (msg.type === 'tunnel.updated' && msg.tunnel.id === tunnelId) {
          setState({ data: msg.tunnel, loading: false, error: null });
        }
        if (msg.type === 'tunnel.log' && msg.tunnel_id === tunnelId) {
          setLogs((prev) => [...prev, msg.log]);
        }
      },
      [tunnelId, setState]
    )
  );

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  function handleScroll() {
    const el = logContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(distanceFromBottom < SCROLL_BOTTOM_THRESHOLD);
  }

  function jumpToBottom() {
    setAutoScroll(true);
    const el = logContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }

  async function handleStop() {
    if (!tunnelId) return;
    setBusy(true);
    try {
      await stopTunnel(tunnelId);
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function handleStart() {
    if (!tunnelId) return;
    setBusy(true);
    try {
      await startTunnel(tunnelId);
      reload();
    } finally {
      setBusy(false);
    }
  }

  if (!tunnelId) {
    return <div className="p-8 text-sm text-text-secondary">Invalid tunnel id.</div>;
  }

  if (loading && !tunnel) {
    return (
      <div className="flex flex-col gap-4 p-8">
        <SkeletonBlock className="h-8 w-64" />
        <SkeletonBlock className="h-64 w-full" />
      </div>
    );
  }

  if (!tunnel) {
    return (
      <div className="p-8 text-sm text-text-secondary">
        Tunnel not found. <button className="text-accent underline" onClick={() => navigate('/')}>Back to sessions</button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-6 py-4">
        <div>
          <div className="flex items-center gap-2">
            <button onClick={() => navigate('/')} className="text-sm text-text-muted hover:text-text-primary">
              Sessions
            </button>
            <IconArrowRight className="text-text-muted" width={12} height={12} />
            <h1 className="font-mono text-lg font-semibold text-text-primary">{tunnel.label}</h1>
          </div>
          <div className="mt-1 flex items-center gap-3">
            <StatusDot tone={tunnelStatusTone(tunnel.status)} label={tunnel.status} />
            <Badge>{tunnel.kind_display}</Badge>
            {tunnel.agent_name && <span className="text-sm text-text-secondary">via {tunnel.agent_name}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {tunnel.desired_state === 'up' ? (
            <Button variant="danger" onClick={handleStop} disabled={busy}>
              <IconStop /> Stop
            </Button>
          ) : (
            <Button variant="primary" onClick={handleStart} disabled={busy}>
              <IconPlay /> Start
            </Button>
          )}
        </div>
      </header>

      {tunnel.last_error && (
        <div className="mx-6 mt-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
          {tunnel.last_error}
        </div>
      )}

      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden p-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="flex flex-col overflow-hidden rounded-lg border border-border-subtle">
          <div className="flex items-center justify-between border-b border-border-subtle bg-surface px-4 py-2">
            <span className="text-xs font-medium text-text-muted">Log tail</span>
            {!autoScroll && (
              <button
                onClick={jumpToBottom}
                className="rounded-sm border border-border-subtle bg-surface-2 px-2 py-1 text-xs text-text-primary hover:bg-surface"
              >
                Jump to bottom
              </button>
            )}
          </div>
          <div
            ref={logContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto bg-[var(--bg-base)] p-3 font-mono text-xs"
          >
            {logsLoading ? (
              <SkeletonBlock className="h-4 w-1/2" />
            ) : logs.length === 0 ? (
              <div className="p-4 text-text-muted">No log output yet.</div>
            ) : (
              logs.map((log) => (
                <div key={log.id} className="flex gap-2 py-0.5 leading-relaxed">
                  <span className="shrink-0 text-text-muted">{formatAbsoluteTime(log.created_at)}</span>
                  <span
                    className="shrink-0 w-16 uppercase"
                    style={{ color: levelColor(log.level as LogLevel) }}
                  >
                    {log.level}
                  </span>
                  <span className="text-text-secondary">[{log.source}]</span>
                  <span className="whitespace-pre-wrap break-all text-text-primary">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="flex flex-col gap-4 overflow-y-auto pr-1">
          <MetadataCard tunnel={tunnel} />
          {tunnel.kind === 'ssh_dynamic' && (
            <>
              <ReachableCard tunnelId={tunnel.id} />
              <ProxychainsCard tunnelId={tunnel.id} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function MetadataCard({ tunnel }: { tunnel: NonNullable<ReturnType<typeof useTunnel>['data']> }) {
  const specEntries = Object.entries(tunnel.spec ?? {});
  return (
    <div className="rounded-lg border border-border-subtle p-4">
      <h2 className="mb-3 text-xs font-medium text-text-muted">Metadata</h2>
      <dl className="grid grid-cols-2 gap-y-2 text-sm">
        <dt className="text-text-secondary">PID</dt>
        <dd className="font-mono text-text-primary">{tunnel.pid ?? '—'}</dd>
        <dt className="text-text-secondary">Restarts</dt>
        <dd className="font-mono text-text-primary">{tunnel.restart_count}</dd>
        <dt className="text-text-secondary">Started</dt>
        <dd className="font-mono text-text-primary">{formatAbsoluteTime(tunnel.started_at)}</dd>
        <dt className="text-text-secondary">Stopped</dt>
        <dd className="font-mono text-text-primary">{formatAbsoluteTime(tunnel.stopped_at)}</dd>
        <dt className="text-text-secondary">Uptime</dt>
        <dd className="font-mono text-text-primary">{formatDuration(tunnel.uptime_seconds)}</dd>
        <dt className="text-text-secondary">Created by</dt>
        <dd className="font-mono text-text-primary">{tunnel.created_by_name}</dd>
      </dl>
      {specEntries.length > 0 && (
        <div className="mt-3 border-t border-border-subtle pt-3">
          <div className="mb-2 text-xs font-medium text-text-muted">Spec</div>
          <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
            {specEntries.map(([key, value]) => (
              <Fragment key={key}>
                <dt className="text-text-secondary">{key}</dt>
                <dd className="truncate font-mono text-text-primary">{String(value)}</dd>
              </Fragment>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function ReachableCard({ tunnelId }: { tunnelId: number }) {
  const [data, setData] = useState<ReachableResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeSensitive, setIncludeSensitive] = useState(false);
  const [exposing, setExposing] = useState(false);
  const [exposeCount, setExposeCount] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    getReachable(tunnelId)
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load reachable hosts.'))
      .finally(() => setLoading(false));
  }, [tunnelId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleExposeAll() {
    setExposing(true);
    setError(null);
    setExposeCount(null);
    try {
      const res = await autoExpose(tunnelId, { include_sensitive: includeSensitive });
      setExposeCount(res.count);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to auto-expose services.');
    } finally {
      setExposing(false);
    }
  }

  return (
    <div className="rounded-lg border border-border-subtle p-4">
      <h2 className="mb-3 text-xs font-medium text-text-muted">Reachable through this pivot</h2>

      {loading ? (
        <SkeletonBlock className="h-16 w-full" />
      ) : !data || (data.subnets.length === 0 && data.hosts.length === 0) ? (
        <p className="text-sm text-text-muted">
          Nothing found yet. Run an nmap scan through this tunnel to discover what's reachable.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <div className="mb-1.5 text-xs font-medium text-text-muted">Subnets opened</div>
            <div className="flex flex-wrap gap-1">
              {data.subnets.map((cidr) => (
                <Badge key={cidr} mono>
                  {cidr}
                </Badge>
              ))}
            </div>
          </div>
          <ul className="flex flex-col gap-1.5">
            {data.hosts.map((host) => (
              <li key={host.host} className="rounded-md border border-border-subtle px-2.5 py-1.5">
                <div className="font-mono text-sm text-text-primary">
                  {host.host} {host.hostname && <span className="text-text-muted">({host.hostname})</span>}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {host.open_ports.map((port) => (
                    <Badge key={port} mono>
                      {port}
                    </Badge>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <div className="mt-3 text-xs text-error">{error}</div>}
      {exposeCount !== null && (
        <div className="mt-3 text-xs text-ok">
          Exposed {exposeCount} service{exposeCount === 1 ? '' : 's'} as local port-forwards.
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-3 border-t border-border-subtle pt-3">
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          <input
            type="checkbox"
            checked={includeSensitive}
            onChange={(e) => setIncludeSensitive(e.target.checked)}
            style={{ accentColor: 'var(--accent)' }}
          />
          Include sensitive ports (22, 3389, 5985, 623 are skipped by default)
        </label>
        <Button
          size="sm"
          variant="primary"
          onClick={handleExposeAll}
          disabled={exposing || !data || data.hosts.length === 0}
        >
          {exposing ? 'Exposing…' : 'Expose all'}
        </Button>
      </div>
    </div>
  );
}

function ProxychainsCard({ tunnelId }: { tunnelId: number }) {
  const [config, setConfig] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    getProxychains(tunnelId)
      .then((res) => {
        setConfig(res.config);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load proxychains config.'))
      .finally(() => setLoading(false));
  }, [tunnelId]);

  async function handleCopy() {
    if (!config) return;
    await navigator.clipboard.writeText(config);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-lg border border-border-subtle p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-medium text-text-muted">proxychains</h2>
        {config && (
          <Button size="sm" onClick={handleCopy}>
            {copied ? 'Copied' : 'Copy'}
          </Button>
        )}
      </div>

      {loading ? (
        <SkeletonBlock className="h-16 w-full" />
      ) : error ? (
        <div className="text-xs text-error">{error}</div>
      ) : (
        <>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border border-border-subtle bg-[var(--bg-base)] p-3 font-mono text-xs text-text-primary">
            {config}
          </pre>
          <p className="mt-2 font-mono text-xs text-text-muted">proxychains4 -f mudale.conf nmap -sT -Pn &lt;target&gt;</p>
        </>
      )}
    </div>
  );
}
