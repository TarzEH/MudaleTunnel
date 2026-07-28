# Security model

This tool opens network access into other people's infrastructure and runs a
port scanner. The controls below are the ones that keep that honest.

## Threat model

Assumed:

- Operators are trusted but fallible. The system should make an out-of-scope
  action *hard*, and make it *visible* when attempted.
- The dashboard may be reachable by someone who should not have it. It must not
  be usable without authentication, and one team must not see another's
  engagement.
- **Targets are hostile.** Anything a scanned host says — service banners,
  hostnames, XML — is attacker-controlled input.
- The engine host is trusted. An operator who can run `enginectl` can already
  run `ssh` directly; the control plane is not a sandbox around them.

Out of scope: defending against a compromised engine host, or against an
operator with database access.

## 1. Engagement scope

`Engagement.authorized_cidrs` is the root of authorisation. Every scan target,
tunnel endpoint and route passes through `apps/engagements/scope.py`.

**A new engagement is inert.** With no authorised CIDRs, every target is out of
scope. Widening is a deliberate act, and gets its own audit action
(`engagement.scope_changed`) recording before and after.

**Containment must be total.** A `/16` allowance does not permit a `/8` target
even though they overlap — partial overlap fails closed. Otherwise "scan
10.0.0.0/8" would be permitted by an allowance of 10.4.0.0/16 and would sweep
the client's entire private space.

**Scope expires on its own.** A paused, closed, not-yet-started or past-end-date
engagement authorises nothing, without anyone having to remember to switch it
off.

**Hostnames are resolved and every answer must be in scope.** A name that
answers with even one out-of-scope address is rejected rather than partially
allowed. This is best-effort — DNS can change between the check and the connect
— so prefer literal addresses and CIDRs.

### What is deliberately *not* scope-checked

- `local_bind` on a local forward: an address on the operator's own machine.
  Binding 127.0.0.1 locally is not "touching" the client.
- `target_host` on a *reverse* forward: reached from the operator's side, not
  from inside the client network.

## 2. Command injection

v2 appended the scan target verbatim to an nmap argv, from an unauthenticated
endpoint, in a container running as root. `-oN /etc/cron.d/x` was a file write.

Three independent layers now make that unreachable:

1. **Targets become objects.** A target is parsed into an `ipaddress` network
   and the argv is rebuilt from `str(network)`, not from the operator's string.
   A value that is not a network cannot survive the round trip. The adapter
   enforces this at runtime with a type check, not just an annotation.
2. **Profiles, not flags.** Operators pick a named profile; the mapping to nmap
   arguments is a fixed table in code. No user input becomes an nmap option.
   No profile contains `-oN`, `-oX`, `-oG`, `--datadir`, `--script` or `-iL`;
   there is a test asserting this.
3. **`--` before the target.** Even a hypothetical parser bug that let a dash
   through would be read by nmap as a target, not an option.

Nothing is ever executed through a shell. Every subprocess takes an argv list.

For SSH, the same job is done by the spec schema: usernames, hosts and identity
paths that begin with `-` or contain whitespace are rejected, which matters
because `ssh` has no `--` separator and the destination is positional.

## 3. Authentication and authorisation

| | |
|---|---|
| Sessions | Django auth, 12-character minimum, standard hashers |
| API keys | 32 bytes of entropy, stored **only** as SHA-256. Plaintext is shown once and is unrecoverable. Revoked and unknown keys produce an identical error so a caller cannot learn whether a key ever existed. |
| Default | DRF `IsAuthenticated`. Only `/api/v1/health/` is public, and it returns nothing but `{"status": "ok"}`. |
| Roles | `admin`, `operator`, `viewer`. Viewers are read-only everywhere. |
| Isolation | Querysets are filtered by engagement membership. A foreign tunnel is a 404, not a 403 — the id space is not enumerable. |
| WebSockets | Authorised per engagement on connect, and receive-only apart from a keepalive. A missing engagement and a forbidden one close with the same code. |

## 4. The audit trail

Append-only, enforced in the model: `save()` on an existing row and `delete()`
both raise.

- **Survives deletion.** The actor's identity is denormalised at write time, and
  objects are referenced loosely by `(type, id)`, so entries outlive both the
  operator account and the thing they describe.
- **Records refusals.** Denials are written *before* the exception propagates
  and outside the transaction, so a rollback cannot erase them.
- **Names the actor.** Resolved at write time, because authentication runs after
  the audit middleware — otherwise everything is attributed to "system".
- **Redacts credentials.** Keys matching `password`, `token`, `secret`, `key`
  and friends are replaced before storage, and a container named for a
  credential has its whole subtree redacted rather than being walked into.

`X-Forwarded-For` is deliberately ignored when recording a source IP: it is
trivially spoofable unless a trusted proxy overwrites it, and a forged address
in an audit trail is worse than no address.

## 5. Hostile input from targets

nmap output is a document written, in part, by the host being scanned.

- Parsed with `defusedxml`, which refuses entity declarations outright — closing
  billion-laughs and external-entity attacks.
- Banners are truncated to column widths and stripped of control characters, so
  a crafted banner cannot inject line breaks or escapes into logs and CLI output.
- Impossible ports and malformed addresses are dropped.
- A malformed document is a **scan failure**, not an empty result. v2's text
  parser returned zero services whenever the output shape surprised it, so a
  broken parse looked exactly like a clean scan that found nothing.

Nothing parsed from a target is ever used to build a command line.

## 6. Deployment

- **Unprivileged container.** Runs as `mudale` (uid 10001).
- **Loopback by default.** The dashboard publishes to `127.0.0.1:8000`; the
  database and Redis are not published at all.
- **Production settings refuse to start** on a wildcard `ALLOWED_HOSTS` or a
  missing database password, rather than running in a weak state. CI asserts
  this.
- **Secure defaults**: HSTS, secure cookies, `SameSite=Lax`, `X-Frame-Options:
  DENY`, `nosniff`. `dev.py` relaxes only the transport-security settings that
  would break a plain-HTTP dev loop — never authentication.
- **Admin path is configurable** via `MUDALE_ADMIN_PATH` so it is not on a
  guessable URL in a deployment reachable from a client network.
- **Private keys are never stored.** The ssh adapter takes a *path* on the
  engine host; the compose file mounts `~/.ssh` read-only.

### Things to get right yourself

- Put a TLS terminator in front before exposing this beyond loopback.
- `network_mode: host` for the engine drops network isolation. It is sometimes
  the pragmatic choice on Linux; treat it as a deliberate trade-off.
- Rotate API keys at the end of an engagement.
- The database holds client scope and findings. Encrypt it at rest and back it
  up accordingly.

## Reporting a vulnerability

Open a private security advisory on the repository, or email the maintainer.
Please do not open a public issue for anything exploitable.
