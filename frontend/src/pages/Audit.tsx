import { useMemo, useState } from 'react';
import { useEngagementContext } from '../context/EngagementContext';
import { useAudit } from '../api/hooks';
import { Badge } from '../components/Badge';
import { EmptyState } from '../components/EmptyState';
import { TextInput } from '../components/Form';
import { IconLogs } from '../components/icons';
import { SkeletonRows } from '../components/Skeleton';
import { formatAbsoluteTime } from '../utils/time';

const RESULT_OPTIONS = ['', 'success', 'denied', 'error'];

export function Audit() {
  const { selected, selectedId } = useEngagementContext();
  const [action, setAction] = useState('');
  const [result, setResult] = useState('');
  const [date, setDate] = useState('');

  const { items, loading, error } = useAudit({
    engagement: selectedId,
    action: action || null,
    result: result || null,
  });

  const filtered = useMemo(() => {
    if (!date) return items;
    return items.filter((event) => event.created_at.slice(0, 10) === date);
  }, [items, date]);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Audit</h1>
        <p className="text-sm text-text-secondary">
          Action log {selected ? `for ${selected.name}` : 'across all engagements'}
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3 border-b border-border-subtle px-6 py-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="audit-action">
            Action
          </label>
          <TextInput
            id="audit-action"
            data-filter-focus
            value={action}
            onChange={(e) => setAction(e.target.value)}
            placeholder="tunnel.start"
            mono
            className="w-48"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="audit-result">
            Result
          </label>
          <select
            id="audit-result"
            value={result}
            onChange={(e) => setResult(e.target.value)}
            className="h-9 rounded-md border border-border-subtle bg-base px-2.5 text-sm text-text-primary focus-visible:border-accent"
          >
            {RESULT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt || 'All results'}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-text-secondary" htmlFor="audit-date">
            Date
          </label>
          <input
            id="audit-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="h-9 rounded-md border border-border-subtle bg-base px-2.5 text-sm text-text-primary focus-visible:border-accent"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto px-6 py-4">
        {error && (
          <div className="mb-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error.message}
          </div>
        )}

        {!loading && filtered.length === 0 ? (
          <EmptyState icon={<IconLogs width={28} height={28} />} title="No audit events match these filters" />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="px-4 py-2 font-medium">Time</th>
                <th className="px-4 py-2 font-medium">Actor</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Object</th>
                <th className="px-4 py-2 font-medium">Result</th>
                <th className="px-4 py-2 font-medium">Message</th>
                <th className="px-4 py-2 font-medium">Source IP</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={8} columns={7} />
              ) : (
                filtered.map((event) => (
                  <tr key={event.id} className="border-b border-border-subtle hover:bg-surface">
                    <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-text-secondary">
                      {formatAbsoluteTime(event.created_at)}
                    </td>
                    <td className="px-4 py-2.5 text-text-primary">{event.actor_label}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-text-primary">{event.action_display}</td>
                    <td className="px-4 py-2.5 text-text-secondary">
                      {event.object_type ? `${event.object_type} ${event.object_label}` : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      {event.result === 'denied' ? (
                        <Badge tone="error">denied</Badge>
                      ) : event.result === 'error' ? (
                        <Badge tone="warn">error</Badge>
                      ) : (
                        <span className="text-text-secondary">{event.result}</span>
                      )}
                    </td>
                    <td className="max-w-md truncate px-4 py-2.5 text-text-secondary">{event.message}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-text-secondary">
                      {event.source_ip || '—'}
                    </td>
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
