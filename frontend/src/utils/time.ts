/** Formats an ISO timestamp as a short relative time, e.g. "3m ago", "in 2h". */
export function formatRelativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffMs = now - then;
  const future = diffMs < 0;
  const diffSec = Math.round(Math.abs(diffMs) / 1000);

  const units: [number, string][] = [
    [60, 's'],
    [60, 'm'],
    [24, 'h'],
    [365, 'd'],
    [Number.MAX_SAFE_INTEGER, 'y'],
  ];

  let value = diffSec;
  let label = 's';
  for (const [span, unit] of units) {
    if (value < span) {
      label = unit;
      break;
    }
    value = Math.floor(value / span);
    label = unit;
  }

  if (diffSec < 5) return 'just now';
  return future ? `in ${value}${label}` : `${value}${label} ago`;
}

/** Formats a duration in seconds as "1h 24m", "45s", etc. */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) return '—';
  const s = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function formatAbsoluteTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
