<p align="center">
  <img src="docs/mudaletunnel-banner.svg" alt="MudaleTunnel" width="720">
</p>

<p align="center">
  <strong>A control plane for network pivoting.</strong><br>
  Manages SSH tunnels and network discovery across an engagement, from a CLI and a web dashboard that share one API.
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> &bull;
  <a href="#using-it">Using it</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#security">Security</a> &bull;
  <a href="#development">Development</a> &bull;
  <a href="#status">Status</a>
</p>

---

## What this is

Tools like [ligolo-ng](https://github.com/nicocha30/ligolo-ng) are very good at
*moving packets*. What they don't give you is the layer around that: state that
survives a restart, an audit trail that says who opened which tunnel into a
client network, more than one operator, and a clear view of where you actually
are.

MudaleTunnel is that layer. It drives tunnel engines rather than reimplementing
them, and adds:

| | |
|---|---|
| **Engagement scope** | An explicit CIDR allowlist per engagement, enforced in code on every scan, tunnel and route. Nothing outside it can be touched. |
| **Durable state** | PostgreSQL. Tunnels, scans, findings and the audit trail survive a restart of any component. |
| **Append-only audit** | Who did what, when — and what was *refused*. Survives operator deletion. |
| **Multiple operators** | Real accounts, roles, per-engagement membership. |
| **One API, two clients** | The CLI and the dashboard make the same calls. A tunnel opened in the terminal appears in the browser immediately. |

> **Authorised testing only.** This tool opens network access into other
> people's infrastructure. The scope allowlist exists to keep you inside what a
> client actually agreed to. It is a safety rail, not permission.

---

## Quick start

```bash
git clone https://github.com/TarzEH/MudaleTunnel.git
cd MudaleTunnel
cp backend/.env.example .env
```

Set `MUDALE_SECRET_KEY` and `MUDALE_DB_PASSWORD` in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Bring it up:

```bash
docker compose up -d --build
```

Create your first operator:

```bash
docker compose exec web python manage.py createsuperuser
```

The dashboard is on <http://127.0.0.1:8000>. It binds to loopback on purpose —
this is a console that opens tunnels into client networks, so exposing it more
widely should be a deliberate act behind a TLS proxy.

For the CLI, issue yourself a key from **Settings → API keys** in the dashboard,
then:

```bash
pip install ./backend
mudale login --url http://127.0.0.1:8000 --token mdlt_...
```

---

## Using it

### 1. Define the engagement

Everything hangs off an engagement, and a new one is **inert**: with no
authorised CIDRs, every target is out of scope until you say otherwise.

```bash
mudale engagement create --name "Acme internal" --client Acme \
  --cidr 10.4.0.0/16 --cidr 192.168.50.0/24
```

### 2. Discover

```bash
mudale scan run --engagement 1 --target 10.4.9.0/24 --profile quick --wait
```

```
12 services on 4 hosts in 34s

HOST       PORT      STATE   SERVICE       VERSION
10.4.9.5   22/tcp    open    ssh           OpenSSH 8.9p1
10.4.9.5   1433/tcp  open    ms-sql-s      Microsoft SQL Server 15.00.2000
10.4.9.12  445/tcp   open    microsoft-ds
```

### 3. Pivot

```bash
mudale tunnel create --engagement 1 --kind ssh_local \
  --ssh-user opsec --ssh-host 10.4.0.10 --identity-file /keys/acme.pem \
  --local-port 1433 --target-host 10.4.9.5 --target-port 1433 \
  --label "sql via jump"
```

The web tier records the request; the engine brings it up and reports back.
Watch it from either side:

```bash
mudale tunnels
mudale tunnel logs 3 --follow
```

### 4. Scan through the pivot

```bash
mudale scan run --engagement 1 --target 10.4.50.0/24 --via-tunnel 3 --wait
```

### Out of scope is out of scope

```console
$ mudale scan run --engagement 1 --target 8.8.8.8 --profile quick
error  8.8.8.8/32 is not fully contained by any authorised range (10.4.0.0/16, 192.168.50.0/24)

$ mudale scan run --engagement 1 --target 10.0.0.0/8 --profile quick
error  10.0.0.0/8 is not fully contained by any authorised range (10.4.0.0/16, 192.168.50.0/24)
```

The second one matters: a `/16` allowance does **not** permit scanning the
enclosing `/8`, even though they overlap. Partial overlap fails closed.

### Tunnel kinds

| Kind | `ssh` equivalent | Use for |
|---|---|---|
| `ssh_local` | `-L` | Reach one remote service locally |
| `ssh_dynamic` | `-D` | SOCKS proxy into the remote network |
| `ssh_remote` | `-R` | Expose a local service to the remote side |
| `ssh_remote_dynamic` | `-R` (SOCKS) | Reverse SOCKS; needs OpenSSH 7.6+ on both ends |

### Scan profiles

Operators pick a profile; raw nmap flags are never accepted.

| Profile | What it does |
|---|---|
| `discovery` | Host sweep, no port scan |
| `quick` | Top 100 ports |
| `standard` | Top 1000 ports with version detection |
| `full` | All 65535 TCP ports with version detection |
| `udp_top` | Top 100 UDP ports (needs root on the engine host) |

All default profiles use `connect()` scans, so they work unprivileged and
through a pivot. No profile can write to a path or run NSE scripts.

---

## Architecture

```
┌──────────────┐        ┌──────────────┐
│  mudale CLI  │        │  Dashboard   │
└──────┬───────┘        └──────┬───────┘
       │   REST + WebSocket    │
       └───────────┬───────────┘
                   ▼
        ┌──────────────────────┐
        │  Django (ASGI)       │
        │  ├── API + auth      │
        │  ├── service layer   │ ← scope checks, roles, audit
        │  └── Channels        │
        └───────┬──────────────┘
                │  desired state
        ┌───────▼──────────────┐      ┌─────────────┐
        │  PostgreSQL + Redis  │◄─────┤  enginectl  │ ← owns every subprocess
        └──────────────────────┘      └──────┬──────┘
                observed state                │
                                        ssh · nmap
```

**The web tier never spawns a process.** It records what an operator *wants*;
the engine daemon reconciles reality towards it and writes back what *is*.

That split is why the system is survivable. A gunicorn or daphne worker is
recycled on every deploy and under load — a tunnel living inside one would be
killed or orphaned by that. Keeping the daemon separate lets the web tier
restart freely while tunnels stay up, and lets the engine restart and re-adopt
what it finds instead of leaving strays behind.

Full detail, including how process ownership and adoption work:
[`docs/architecture.md`](docs/architecture.md).

---

## Security

The full model is in [`docs/security.md`](docs/security.md). In short:

- **Scope is enforced in code, not by convention.** Targets are parsed into
  `ipaddress` objects and the command line is rebuilt *from those objects*, so a
  string that is not an address or network can never reach an argv.
- **Authentication everywhere.** Sessions or hashed API keys; DRF defaults to
  `IsAuthenticated`; WebSockets are authorised per engagement on connect and are
  receive-only.
- **Cross-engagement isolation** is enforced on the queryset, not by trusting an
  id in the URL.
- **The audit trail is append-only**, records denials, and names the actor.
- **The container runs unprivileged**, and nmap output is parsed with hardened
  XML bindings because service banners come from the target.

To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

---

## Development

```bash
# Backing services only; the app runs on the host
docker compose -f docker-compose.dev.yml up -d

cd backend
uv venv && uv pip install -e ".[dev]"
export MUDALE_SECRET_KEY=dev-only MUDALE_DB_PASSWORD=mudale-dev-password
python manage.py migrate
python manage.py runserver     # terminal 1
python manage.py enginectl     # terminal 2

cd ../frontend
npm install && npm run dev     # terminal 3, proxies /api to :8000
```

```bash
cd backend  && pytest -q && ruff check .
cd frontend && npx tsc --noEmit && npm run build
```

Layout and conventions: [`docs/development.md`](docs/development.md).

---

## Status

**Working:** SSH tunnels (all four kinds), nmap discovery directly or through a
pivot, engagement scoping, the audit trail, the dashboard, the CLI, and
multi-operator access.

**Not yet:** the ligolo-ng adapter is a stub. The models and API already
describe it, but the engine cannot drive a ligolo proxy, so there is no
TUN-interface pivoting and no full TCP/UDP/ICMP routing yet. Routes and
listeners are modelled, scope-checked and stored, but only take effect for
engines that implement them — which today means neither.

Version 3 is a rewrite; versions 1–2 share nothing with it but the name and the
idea. [`docs/architecture.md`](docs/architecture.md) records what changed and
why.

## Licence

MIT — see [LICENSE](LICENSE).
