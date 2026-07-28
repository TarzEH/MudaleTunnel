export type StatusTone = 'ok' | 'warn' | 'error' | 'info' | 'neutral';

const TONE_COLOR: Record<StatusTone, string> = {
  ok: 'var(--status-ok)',
  warn: 'var(--status-warn)',
  error: 'var(--status-error)',
  info: 'var(--status-info)',
  neutral: 'var(--text-muted)',
};

interface StatusDotProps {
  tone: StatusTone;
  label: string;
  className?: string;
}

/** An 8px status dot with a text label. No glow, no shadow, per design spec. */
export function StatusDot({ tone, label, className = '' }: StatusDotProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span
        className="inline-block h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: TONE_COLOR[tone] }}
        aria-hidden="true"
      />
      <span className="text-sm text-text-secondary">{label}</span>
    </span>
  );
}

export function tunnelStatusTone(status: string): StatusTone {
  switch (status) {
    case 'active':
      return 'ok';
    case 'starting':
    case 'stopping':
    case 'pending':
      return 'warn';
    case 'degraded':
      return 'warn';
    case 'failed':
      return 'error';
    case 'stopped':
      return 'neutral';
    default:
      return 'neutral';
  }
}

export function agentStatusTone(status: string): StatusTone {
  switch (status) {
    case 'online':
      return 'ok';
    case 'pending':
      return 'warn';
    case 'offline':
      return 'neutral';
    case 'retired':
      return 'error';
    default:
      return 'neutral';
  }
}

export function scanStatusTone(status: string): StatusTone {
  switch (status) {
    case 'completed':
      return 'ok';
    case 'running':
    case 'queued':
      return 'warn';
    case 'failed':
    case 'timed_out':
      return 'error';
    case 'cancelled':
      return 'neutral';
    default:
      return 'neutral';
  }
}

export function engagementStatusTone(status: string): StatusTone {
  switch (status) {
    case 'active':
      return 'ok';
    case 'planned':
      return 'info';
    case 'paused':
      return 'warn';
    case 'closed':
      return 'neutral';
    default:
      return 'neutral';
  }
}
