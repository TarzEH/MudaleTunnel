# Security policy

## Reporting a vulnerability

Please open a [private security advisory](https://github.com/TarzEH/MudaleTunnel/security/advisories/new)
rather than a public issue for anything exploitable.

Useful to include: what an attacker gains, the smallest reproduction you have,
and which version or commit you tested.

## Scope

In scope — anything that lets someone:

- act outside an engagement's `authorized_cidrs`;
- get a value they control onto a command line;
- read or modify another engagement's data;
- reach any endpoint other than `/api/v1/health/` without authenticating;
- suppress, forge or erase an audit entry;
- escalate from the container to the host.

Out of scope:

- An operator with database access. They can already rewrite anything.
- A compromised engine host. Someone who can run `enginectl` can run `ssh`
  directly; the control plane is not a sandbox around the operator.
- Findings that require `network_mode: host`, which is documented as a
  deliberate trade-off.

## Intended use

MudaleTunnel is for authorised security testing. The engagement scope allowlist
exists to keep an authorised operator inside what a client actually agreed to.

It is a safety rail, not an authorisation to test anything.

## Supported versions

| Version | Supported |
|---|---|
| 3.x | Yes |
| 2.x and earlier | No — and do not run them. See [`docs/architecture.md`](docs/architecture.md) for why. |
