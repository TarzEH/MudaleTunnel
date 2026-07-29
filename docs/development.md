# Development

## Layout

```
backend/
  mudale/            Django project — settings, urls, asgi, routing
    settings/        base · dev · prod · test  (+ typed env readers)
  apps/
    accounts/        Operator, API keys, authentication
    engagements/     Engagement + scope.py  ← the authorisation core
    agents/          Footholds you pivot through
    tunnels/         Tunnel · TunnelLog + services.py + pivot.py
    scans/           Scan · Service + parsers.py + services.py
    audit/           Append-only trail, context, middleware
    engine/          specs · process · adapters/ · supervisor · enginectl
    api/             serializers · views · urls · consumers · broadcast · spa
  mudale_cli/        The `mudale` command
frontend/            React + Vite + TypeScript + Tailwind
docs/
```

## Running it

```bash
docker compose -f docker-compose.dev.yml up -d    # postgres + redis on loopback

cd backend
uv venv && uv pip install -e ".[dev]"
export MUDALE_SECRET_KEY=dev-only MUDALE_DB_PASSWORD=mudale-dev-password
python manage.py migrate
python manage.py createsuperuser

python manage.py runserver          # terminal 1
python manage.py enginectl          # terminal 2

cd ../frontend && npm install && npm run dev   # terminal 3 → :5173, proxies /api
```

`enginectl --once` runs a single reconciliation pass and exits, which is handy
when you want to step through it.

## Tests

```bash
cd backend && pytest -q
```

They run against a real PostgreSQL, not SQLite: the scope allowlist is an
`ArrayField` and audit payloads are `JSONB`, so SQLite would exercise different
code than production.

Some tests deliberately use real subprocesses rather than mocks, because the
defects worth catching live in the gap between what the code assumes about
process lifecycle and what the OS actually does:

- `apps/engine/tests/test_process.py` — spawns real `sh`/`python` children to
  check group termination, SIGKILL escalation, and that a chatty process cannot
  deadlock on a full pipe.
- `apps/engine/tests/test_ssh_integration.py` — starts a real user-mode `sshd`,
  brings a real SOCKS tunnel up, and pushes a real SOCKS5 handshake through it.
  Skips itself if the environment cannot support that.

```bash
cd backend  && ruff check .
cd frontend && npx tsc --noEmit && npm run build
```

## Conventions

**Mutations go through the service layer.** Views and CLI commands call
`apps/*/services.py`; they never call `.save()` on an operational model. That is
what keeps scope checks, role checks and audit on the path of every caller.

**The API never writes `status`; the engine never writes `desired_state`.** See
[architecture.md](architecture.md) — this rule is load-bearing.

**Nothing user-supplied reaches a command line as a string.** Parse it into an
object and rebuild the argv from the object.

**Comments explain why, not what.** Most of the non-obvious comments in this
codebase mark places where the obvious implementation is wrong — the
`ClearAllForwardings` trap, the transaction shape around denial auditing, the
choice of pub/sub channel layer. Those are worth preserving.

**Tests assert behaviour, not shape.** Asserting that a flag appears in an argv
is not the same as asserting the tunnel works; that exact gap let a real bug
through.

## Adding a tunnel engine

1. Add a spec model in `apps/engine/specs.py` and register it in `SPEC_BY_KIND`.
2. Add the kind to `TunnelKind`, and its scoped host fields to
   `SCOPED_HOST_FIELDS` in `apps/tunnels/services.py`.
3. Write an adapter in `apps/engine/adapters/` exposing `is_available()`,
   `plan()` and `interpret_exit()`.
4. Wire it into `Supervisor._start_tunnel`.
5. Test the argv construction, and add an integration test that proves the
   tunnel actually carries traffic. Asserting on argv alone is not enough — see
   the `ClearAllForwardings` note in [architecture.md](architecture.md).

## Migrations

```bash
python manage.py makemigrations
python manage.py makemigrations --check --dry-run   # what CI runs
```

CI fails on a model change that was never turned into a migration, which
otherwise only surfaces as a runtime error after deploy.

## Environment variables

Every setting is read through the typed helpers in `mudale/settings/env.py`, so
a missing or malformed value fails loudly at import rather than defaulting to
something insecure. `backend/.env.example` lists them all.
