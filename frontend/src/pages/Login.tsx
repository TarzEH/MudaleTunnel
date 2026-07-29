import { FormEvent, useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';
import { login } from '../api/hooks';
import type { Bootstrap, Me } from '../api/types';
import { Button } from '../components/Button';

interface Props {
  onSignedIn: (me: Me) => void;
}

/**
 * Sign-in screen.
 *
 * Deliberately spare: this is the boundary in front of a tool that opens
 * tunnels into client networks, so it shows nothing about the deployment —
 * no engagement names, no operator list, no version — to anyone who has not
 * authenticated yet.
 */
export function Login({ onSignedIn }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<Bootstrap>('/bootstrap/')
      .then((value) => {
        if (!cancelled) setBootstrap(value);
      })
      .catch(() => {
        // A deployment that does not expose bootstrap is a normal deployment.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const demo = bootstrap?.demo_credentials ?? null;

  function useDemoCredentials() {
    if (!demo) return;
    setUsername(demo.username);
    setPassword(demo.password);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await login(username, password));
    } catch (err) {
      // The server returns the same message for an unknown user and a wrong
      // password; keep it that way rather than adding detail here.
      setError(err instanceof ApiError ? err.detail : 'Could not reach the server.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-base px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <h1 className="text-lg font-semibold text-text-primary">MudaleTunnel</h1>
          <p className="mt-1 text-sm text-text-muted">Sign in to continue.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="username" className="mb-1.5 block text-sm text-text-secondary">
              Operator
            </label>
            <input
              id="username"
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm text-text-primary outline-none focus-visible:border-accent focus-visible:ring-1 focus-visible:ring-accent"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm text-text-secondary">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-subtle bg-surface px-3 py-2 text-sm text-text-primary outline-none focus-visible:border-accent focus-visible:ring-1 focus-visible:ring-accent"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md border border-subtle px-3 py-2 text-sm text-error">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={busy} className="w-full justify-center">
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        {demo && (
          <div className="mt-6 rounded-md border border-subtle bg-surface p-3">
            <div className="mb-2 flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-warn" aria-hidden="true" />
              <span className="text-xs font-medium text-text-secondary">
                Demo credentials
              </span>
            </div>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="w-20 text-text-muted">username</dt>
                <dd className="font-mono text-text-primary">{demo.username}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 text-text-muted">password</dt>
                <dd className="font-mono text-text-primary">{demo.password}</dd>
              </div>
            </dl>
            <button
              type="button"
              onClick={useDemoCredentials}
              className="mt-2 text-xs text-accent underline-offset-2 hover:underline focus-visible:underline"
            >
              Fill them in
            </button>
            <p className="mt-2 text-xs text-text-muted">
              Shown because this deployment is loopback-only. Change the password before
              exposing it anywhere.
            </p>
          </div>
        )}

        {bootstrap?.demo_suppressed && (
          <p className="mt-6 rounded-md border border-subtle px-3 py-2 text-xs text-text-muted">
            Demo credentials are configured but withheld: this deployment is reachable
            beyond loopback.
          </p>
        )}

        <p className="mt-6 text-xs text-text-muted">
          Using an API key instead? Set it under Settings once signed in, or pass it as a
          <code className="mx-1 font-mono">Bearer</code> token from the CLI.
        </p>
      </div>
    </div>
  );
}
