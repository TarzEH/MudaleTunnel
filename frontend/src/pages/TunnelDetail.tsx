import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  addListener,
  addRoute,
  deleteListener,
  deleteRoute,
  fetchTunnelLogs,
  startTunnel,
  stopTunnel,
  useTunnel,
} from '../api/hooks';
import { ApiError } from '../api/client';
import { useSocketSubscription } from '../context/SocketContext';
import type { Listener, LogLevel, Route, TunnelLog } from '../api/types';
import { Badge } from '../components/Badge';
import { Button, IconButton } from '../components/Button';
import { Field, TextInput, Select } from '../components/Form';
import { IconArrowRight, IconPlay, IconPlus, IconStop, IconTrash, IconX } from '../components/icons';
import { SkeletonBlock } from '../components/Skeleton';
import { StatusDot, tunnelStatusTone } from '../components/StatusDot';
import { formatAbsoluteTime, formatDuration } from '../utils/time';
import { isValidCidr } from '../utils/cidr';

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
          <RoutesCard tunnelId={tunnel.id} routes={tunnel.routes} onChange={reload} />
          <ListenersCard tunnelId={tunnel.id} listeners={tunnel.listeners} onChange={reload} />
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

function RoutesCard({
  tunnelId,
  routes,
  onChange,
}: {
  tunnelId: number;
  routes: Route[];
  onChange: () => void;
}) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleAdd() {
    if (!isValidCidr(draft.trim())) {
      setError('Enter a valid CIDR, e.g. 10.0.0.0/24');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await addRoute(tunnelId, draft.trim());
      setDraft('');
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to add route.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(routeId: number) {
    await deleteRoute(routeId);
    onChange();
  }

  return (
    <div className="rounded-lg border border-border-subtle p-4">
      <h2 className="mb-3 text-xs font-medium text-text-muted">Routes</h2>
      <ul className="flex flex-col gap-1.5">
        {routes.length === 0 && <li className="text-sm text-text-muted">No routes.</li>}
        {routes.map((route) => (
          <li
            key={route.id}
            className="flex items-center justify-between rounded-md border border-border-subtle px-2.5 py-1.5"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm text-text-primary">{route.cidr}</span>
              {route.discovered && <Badge tone="info">discovered</Badge>}
              <span className="text-xs text-text-muted">{route.status}</span>
            </div>
            <IconButton aria-label={`Remove route ${route.cidr}`} onClick={() => handleRemove(route.id)}>
              <IconTrash />
            </IconButton>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-start gap-2">
        <div className="flex-1">
          <TextInput
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              setError(null);
            }}
            placeholder="10.0.0.0/24"
            mono
            className="w-full"
          />
          {error && <div className="mt-1 text-xs text-error">{error}</div>}
        </div>
        <Button size="sm" onClick={handleAdd} disabled={submitting || !draft.trim()}>
          <IconPlus /> Add
        </Button>
      </div>
    </div>
  );
}

const PROTOCOLS = ['tcp', 'udp'];

function ListenersCard({
  tunnelId,
  listeners,
  onChange,
}: {
  tunnelId: number;
  listeners: Listener[];
  onChange: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [label, setLabel] = useState('');
  const [bindHost, setBindHost] = useState('127.0.0.1');
  const [bindPort, setBindPort] = useState('');
  const [toHost, setToHost] = useState('');
  const [toPort, setToPort] = useState('');
  const [protocol, setProtocol] = useState('tcp');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleAdd() {
    if (!bindPort || !toHost || !toPort) {
      setError('Bind port, target host, and target port are required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await addListener(tunnelId, {
        label: label.trim() || `listener-${bindPort}`,
        bind_host: bindHost.trim() || '127.0.0.1',
        bind_port: Number(bindPort),
        to_host: toHost.trim(),
        to_port: Number(toPort),
        protocol,
      });
      setShowForm(false);
      setLabel('');
      setBindPort('');
      setToHost('');
      setToPort('');
      onChange();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to add listener.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(listenerId: number) {
    await deleteListener(listenerId);
    onChange();
  }

  return (
    <div className="rounded-lg border border-border-subtle p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-medium text-text-muted">Listeners</h2>
        {!showForm && (
          <IconButton aria-label="Add listener" onClick={() => setShowForm(true)}>
            <IconPlus />
          </IconButton>
        )}
      </div>
      <ul className="flex flex-col gap-1.5">
        {listeners.length === 0 && <li className="text-sm text-text-muted">No listeners.</li>}
        {listeners.map((listener) => (
          <li
            key={listener.id}
            className="flex items-center justify-between rounded-md border border-border-subtle px-2.5 py-1.5"
          >
            <div className="flex flex-col">
              <span className="text-sm text-text-primary">{listener.label}</span>
              <span className="font-mono text-xs text-text-secondary">
                {listener.bind_host}:{listener.bind_port} → {listener.to_host}:{listener.to_port} (
                {listener.protocol})
              </span>
            </div>
            <IconButton aria-label={`Remove listener ${listener.label}`} onClick={() => handleRemove(listener.id)}>
              <IconTrash />
            </IconButton>
          </li>
        ))}
      </ul>

      {showForm && (
        <div className="mt-3 flex flex-col gap-2 rounded-md border border-border-subtle p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-muted">New listener</span>
            <IconButton aria-label="Cancel new listener" onClick={() => setShowForm(false)}>
              <IconX />
            </IconButton>
          </div>
          <Field label="Label">
            <TextInput value={label} onChange={(e) => setLabel(e.target.value)} mono />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Bind host">
              <TextInput value={bindHost} onChange={(e) => setBindHost(e.target.value)} mono />
            </Field>
            <Field label="Bind port">
              <TextInput value={bindPort} onChange={(e) => setBindPort(e.target.value)} mono inputMode="numeric" />
            </Field>
            <Field label="Target host">
              <TextInput value={toHost} onChange={(e) => setToHost(e.target.value)} mono />
            </Field>
            <Field label="Target port">
              <TextInput value={toPort} onChange={(e) => setToPort(e.target.value)} mono inputMode="numeric" />
            </Field>
          </div>
          <Field label="Protocol">
            <Select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
              {PROTOCOLS.map((p) => (
                <option key={p} value={p}>
                  {p.toUpperCase()}
                </option>
              ))}
            </Select>
          </Field>
          {error && <div className="text-xs text-error">{error}</div>}
          <Button size="sm" variant="primary" onClick={handleAdd} disabled={submitting}>
            Add listener
          </Button>
        </div>
      )}
    </div>
  );
}
