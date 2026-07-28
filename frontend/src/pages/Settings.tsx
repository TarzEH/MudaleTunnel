import { useState } from 'react';
import { useEngineStatus, useMe } from '../api/hooks';
import { getStoredApiKey, setStoredApiKey } from '../api/client';
import { Badge } from '../components/Badge';
import { Button } from '../components/Button';
import { Field, TextInput } from '../components/Form';
import { IconMoon, IconSun } from '../components/icons';
import { SkeletonBlock } from '../components/Skeleton';
import { StatusDot } from '../components/StatusDot';
import { useTheme } from '../context/ThemeContext';
import { formatRelativeTime } from '../utils/time';

export function Settings() {
  const { theme, toggleTheme } = useTheme();
  const { data: me } = useMe();
  const { data: engineStatus, loading: engineLoading } = useEngineStatus();
  const [apiKeyDraft, setApiKeyDraft] = useState(() => getStoredApiKey() ?? '');
  const [saved, setSaved] = useState(false);

  function handleSaveApiKey() {
    setStoredApiKey(apiKeyDraft.trim() || null);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border-subtle px-6 py-4">
        <h1 className="text-lg font-semibold text-text-primary">Settings</h1>
        <p className="text-sm text-text-secondary">Appearance, credentials, and engine connectivity</p>
      </header>

      <div className="flex-1 overflow-auto px-6 py-6">
        <div className="grid max-w-2xl grid-cols-1 gap-6">
          <section className="rounded-lg border border-border-subtle p-4">
            <h2 className="mb-3 text-sm font-medium text-text-primary">Appearance</h2>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-text-primary">Theme</div>
                <div className="text-xs text-text-secondary">
                  Currently using {theme === 'dark' ? 'dark' : 'light'} mode.
                </div>
              </div>
              <Button variant="secondary" onClick={toggleTheme} aria-label="Toggle theme">
                {theme === 'dark' ? <IconSun /> : <IconMoon />}
                {theme === 'dark' ? 'Light' : 'Dark'}
              </Button>
            </div>
          </section>

          <section className="rounded-lg border border-border-subtle p-4">
            <h2 className="mb-3 text-sm font-medium text-text-primary">Account</h2>
            {me ? (
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-text-secondary">Callsign</dt>
                <dd className="font-mono text-text-primary">{me.callsign || me.username}</dd>
                <dt className="text-text-secondary">Role</dt>
                <dd>
                  <Badge tone={me.role === 'admin' ? 'info' : 'neutral'}>{me.role}</Badge>
                </dd>
                <dt className="text-text-secondary">Can mutate</dt>
                <dd className="text-text-primary">{me.can_mutate ? 'Yes' : 'No (read-only)'}</dd>
              </dl>
            ) : (
              <SkeletonBlock className="h-16 w-full" />
            )}
          </section>

          <section className="rounded-lg border border-border-subtle p-4">
            <h2 className="mb-3 text-sm font-medium text-text-primary">API key</h2>
            <p className="mb-3 text-xs text-text-secondary">
              Used as a Bearer token for API requests instead of the session cookie. Stored only in this
              browser&apos;s local storage.
            </p>
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Field label="Bearer token" htmlFor="api-key">
                  <TextInput
                    id="api-key"
                    type="password"
                    value={apiKeyDraft}
                    onChange={(e) => setApiKeyDraft(e.target.value)}
                    placeholder="mt_live_…"
                    mono
                    className="w-full"
                  />
                </Field>
              </div>
              <Button variant="primary" onClick={handleSaveApiKey}>
                {saved ? 'Saved' : 'Save'}
              </Button>
            </div>
          </section>

          <section className="rounded-lg border border-border-subtle p-4">
            <h2 className="mb-3 text-sm font-medium text-text-primary">Engine status</h2>
            {engineLoading ? (
              <SkeletonBlock className="h-16 w-full" />
            ) : engineStatus ? (
              <div className="flex flex-col gap-3">
                <StatusDot
                  tone={engineStatus.attached ? 'ok' : 'error'}
                  label={engineStatus.attached ? 'Engine attached' : 'Engine not attached'}
                />
                {engineStatus.instances.length === 0 ? (
                  <div className="text-sm text-text-muted">No engine instances reporting.</div>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {engineStatus.instances.map((instance) => (
                      <li
                        key={instance.instance_id}
                        className="rounded-md border border-border-subtle px-3 py-2 text-sm"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-text-primary">{instance.hostname}</span>
                          <Badge mono>v{instance.version}</Badge>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-secondary">
                          <span>Last heartbeat {formatRelativeTime(instance.last_heartbeat_at)}</span>
                          {instance.capabilities.map((cap) => (
                            <Badge key={cap}>{cap}</Badge>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <div className="text-sm text-text-muted">Unable to load engine status.</div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
