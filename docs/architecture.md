# Architecture

## The central idea

MudaleTunnel splits cleanly in two:

- **The control plane** (Django) decides *what should be true*. It validates,
  authorises, records and answers questions. It never touches a process.
- **The engine** (`manage.py enginectl`) makes it true. It owns every
  subprocess, watches them, and writes back what actually happened.

They communicate only through PostgreSQL. There is no RPC between them, no
socket, no shared memory.

### Why not just run tunnels from the web process?

Because web workers are disposable and tunnels are not.

Gunicorn, uvicorn and daphne all recycle workers — on deploy, on `max-requests`,
under memory pressure. A tunnel process parented to a worker dies or is orphaned
when that happens. That is not a hypothetical: it is precisely how v2 lost track
of live SSH processes and ended up unable to stop them.

With the split:

- Redeploying the web tier does not disturb a single tunnel.
- The engine can crash and restart, and *re-adopt* what it finds.
- The database is the only shared truth, so both sides always agree.

## Desired state vs observed state

Every controllable object carries two fields:

```python
desired_state = "up" | "down"     # written by the API. What the operator wants.
status        = "pending" | "starting" | "active" | "degraded" |
                "stopping" | "stopped" | "failed"   # written by the engine only.
```

The API is not permitted to write `status`, and the engine is not permitted to
write `desired_state`. That single rule prevents the whole class of bug where a
dashboard asserts something nobody asked for.

Concretely: `POST /tunnels/3/stop/` sets `desired_state = down` and returns
immediately. The tunnel keeps reporting `active` until the engine has actually
killed the process and said so.

### The reconciliation loop

Every `RECONCILE_INTERVAL_SECONDS` (default 5), the engine:

1. **Adopts or disowns** rows left by a previous engine run.
2. **Starts** tunnels wanted up that are not running.
3. **Stops** tunnels wanted down that still are.
4. **Reaps** processes that exited on their own, and records why.
5. **Runs** queued scans.
6. **Heartbeats**, so the dashboard can say whether a control plane is attached.

A failure in any step is logged and the loop continues. One bad row must never
stop reconciliation.

## Process ownership

Three rules make "is this tunnel alive?" answerable truthfully.

### No self-backgrounding

`ssh -f` authenticates, forks, and the *original* process exits. Storing that
PID means storing a PID that is about to die — and once reaped, the OS is free
to reuse the number for something unrelated. Signalling it later is how you kill
a process you never started.

Adapters never emit `-f`. ssh stays in the foreground under the supervisor, so
the recorded PID is the real process for the tunnel's entire life.

### Own process group

Children are started with `start_new_session=True`, making each a process-group
leader. Stopping signals the **group**, so anything the child forked goes with
it. It also means a Ctrl-C aimed at the daemon's terminal does not tear down
every live tunnel.

### Exit status is latched once

`poll()` reaps. After the first observed exit, the outcome is cached and the PID
is never touched again.

### Failure is a real signal

`ExitOnForwardFailure=yes` makes ssh exit if a forward cannot be bound. Without
it, ssh stays happily connected while forwarding nothing, and "process alive"
stops meaning "tunnel working".

> A related trap, found by running the thing: `ClearAllForwardings=yes` looks
> like the right way to ignore a user's `ssh_config`, but it clears the
> forwarding *you just requested* too. ssh connects, listens on nothing, and
> reports healthy — with no failure for `ExitOnForwardFailure` to catch. The
> isolation is done with `-F /dev/null` instead. There is an integration test
> that starts a real sshd and pushes a real SOCKS5 handshake through the tunnel,
> because asserting on argv contents did not catch this.

### Adoption after a restart

When the engine starts, it finds rows claiming to be live that it did not start.
It cannot supervise them — there is no pipe and no way to latch their exit — so:

- **PID is gone** → the row is corrected.
- **PID is alive** → marked `degraded` with an explanation, and **left running**.

Killing a live tunnel into a client network on startup would be worse than
reporting that it needs attention.

## The service layer

`apps/tunnels/services.py` and `apps/scans/services.py` are the only way to
mutate operational state. The REST API, the CLI and the admin all go through
them. Views never call `.save()` on a tunnel.

This is what makes the policy enforceable: scope checks, role checks, spec
validation and audit writes live in one place, so a new entry point cannot
accidentally skip them.

### One subtlety worth knowing

Validation and denial-auditing happen **outside** the transaction; only the
successful write is wrapped in one.

Wrapping the whole function instead — the obvious `@transaction.atomic` on the
service function — means that when a scope violation propagates, the rollback
takes the denial record with it. Every blocked attempt would silently vanish
from the audit trail, which is the entry an incident review most needs.

`ATOMIC_REQUESTS` is left off for the same reason: it would re-introduce the
problem from the outside.

## Typed specs

A tunnel's parameters live in a JSON `spec` column, which means they can be
anything until something validates them. `apps/engine/specs.py` is that
something: pydantic models with `extra="forbid"`, so a typo cannot silently
disable a constraint, and with field validators that reject usernames, hosts and
paths that start with `-`.

Adapters build argv lists from the *parsed* model, never from the raw dict.

## Real-time

Channels over Redis, using `RedisPubSubChannelLayer`.

Not the default `RedisChannelLayer` — that models each consumer as a durable
queue and holds a blocking read open against Redis for it, which raises
`TimeoutError` on an idle socket and drops the connection. The symptom is a
dashboard that reports "Live" and never updates.

What this layer actually carries is fan-out: "tunnel 3 changed, tell every
dashboard watching this engagement". Pub/sub has no queue to time out, and
missing a message while disconnected is fine because the dashboard refetches on
reconnect.

Sockets are authorised per engagement on connect and are **receive-only** apart
from a keepalive. The socket must never become a second, unaudited command
channel.

## Data model

```
Operator ──< EngagementMembership >── Engagement
                                          │
                          ┌───────────────┼───────────────┐
                          │               │               │
                        Agent          Tunnel           Scan
                                       │    │             │
                                    Route  Listener    Service
                                       │
                                   TunnelLog

AuditEvent — append-only, references everything loosely by (type, id)
             so it outlives what it describes.
```

`Engagement.authorized_cidrs` is the root of authorisation. Everything else is
checked against it.

## What runs where

| Process | Command | Owns |
|---|---|---|
| `web` | `daphne mudale.asgi:application` | HTTP, WebSockets, the SPA |
| `engine` | `manage.py enginectl` | Every ssh and nmap subprocess |
| `migrate` | `manage.py migrate` | Runs once at startup, then exits |
| `db` | PostgreSQL 17 | All state |
| `redis` | Redis 7 | The channel layer only |

`web` and `engine` are the same image with different commands.

## What changed from v2

v3 shares no code with v2. The audit that prompted the rewrite found:

| v2 | v3 |
|---|---|
| Every tunnel creation and every tunnel listing deadlocked — a non-reentrant lock taken twice on one thread, blocking the whole event loop | No locks in the request path; the web tier does no process work at all |
| `ssh -f` with the pre-fork PID stored: status lied, and stop raised `ProcessLookupError`, leaving live unkillable tunnels | Foreground processes, own process group, latched exit status |
| No authentication of any kind, on a dashboard that runs nmap and opens tunnels | Sessions and hashed API keys; `IsAuthenticated` by default |
| nmap target appended unvalidated to an argv, as root, from an unauthenticated endpoint | Targets parsed to `ipaddress` and the argv rebuilt from the object; profiles are a fixed table |
| WebSocket accepted every handshake | Per-engagement authorisation on connect |
| All state in memory; nothing survived a restart | PostgreSQL |
| No tests; CI checked that modules imported | 238 tests including real-subprocess and real-sshd integration tests, gating the image build |
| Container ran as root | Runs as `mudale` |
