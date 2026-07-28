"""Engagement scope enforcement.

This is the security core of the control plane. Every scan target, tunnel
endpoint and route CIDR passes through here before the engine is allowed to
touch it. It exists to make two classes of mistake impossible:

1. **Argument injection.** The previous generation of this tool appended a raw
   user string to an ``nmap`` argv, so a "target" of ``-oN /etc/cron.d/x`` made
   nmap write an attacker-chosen file. Targets are parsed into real
   ``ipaddress`` objects here and re-serialised from those objects, so a value
   that is not an address or network never reaches a command line.

2. **Out-of-scope traffic.** Scanning or tunnelling to a host the client did not
   authorise is, in most jurisdictions, a crime. Authorisation is expressed as
   an explicit CIDR allowlist on the engagement and checked in code.

The functions raise :class:`ScopeViolation`; callers are expected to let that
propagate to a 4xx rather than catch and continue.
"""

from __future__ import annotations

import ipaddress
import re
import socket

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# RFC 1123 hostname: labels of alphanumerics and hyphens, hyphen not at either
# end, 1-63 chars per label, 253 chars total. Deliberately excludes every shell
# and argv metacharacter, including a leading '-'.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$"
)

MAX_TARGET_LENGTH = 253


class ScopeViolation(Exception):
    """A target is malformed, or outside the engagement's authorised ranges."""


class TargetSyntaxError(ScopeViolation):
    """A target string is not a valid IP address, CIDR network or hostname."""


class OutOfScope(ScopeViolation):
    """A syntactically valid target is not covered by the engagement."""


def parse_network(value: str) -> IPNetwork:
    """Parse a CIDR (or bare address) into a network object.

    A bare address is treated as a single-host network (``/32`` or ``/128``).
    Raises :class:`TargetSyntaxError` on anything else — including nmap's
    ``10.0.0.1-50`` range and ``10.0.0.*`` glob syntax, which are not accepted
    because they cannot be represented as a network and would have to be passed
    through to the command line as an opaque string.
    """
    candidate = _pre_validate(value)
    try:
        # strict=False so 10.0.0.5/24 is accepted and normalised to 10.0.0.0/24
        # rather than rejected for having host bits set.
        return ipaddress.ip_network(candidate, strict=False)
    except ValueError as exc:
        raise TargetSyntaxError(
            f"{value!r} is not a valid IP address or CIDR network. "
            f"Ranges (10.0.0.1-50) and globs (10.0.0.*) are not supported — use CIDR."
        ) from exc


def parse_address(value: str) -> IPAddress:
    """Parse a single IP address. Rejects networks and hostnames."""
    candidate = _pre_validate(value)
    try:
        return ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise TargetSyntaxError(f"{value!r} is not a valid IP address") from exc


def parse_host(value: str) -> IPAddress | str:
    """Parse a target that may be an IP address or a hostname.

    Returns an ``ipaddress`` object for addresses and the normalised (lowercased,
    trailing-dot-stripped) string for hostnames.
    """
    candidate = _pre_validate(value)
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        pass

    if not _HOSTNAME_RE.match(candidate):
        raise TargetSyntaxError(
            f"{value!r} is not a valid IP address or hostname. Hostnames may contain "
            f"only letters, digits, hyphens and dots."
        )
    return candidate.rstrip(".").lower()


def resolve_host(hostname: str) -> list[IPAddress]:
    """Resolve a hostname to every address it currently answers with.

    Note the inherent TOCTOU: DNS can return different answers between this
    check and the moment the engine connects. Scope enforcement for hostnames is
    therefore best-effort; enforcement for literal addresses is exact. Prefer
    addresses and CIDRs in engagement definitions.
    """
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise TargetSyntaxError(f"Could not resolve hostname {hostname!r}") from exc

    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses:
        raise TargetSyntaxError(f"Hostname {hostname!r} resolved to no addresses")
    return sorted(addresses, key=str)


def networks_from_strings(values: list[str]) -> list[IPNetwork]:
    """Parse an engagement's authorised-CIDR list, rejecting the whole list on error."""
    return [parse_network(value) for value in values]


def is_within(target: IPNetwork | IPAddress, allowed: list[IPNetwork]) -> bool:
    """True when ``target`` is fully contained by at least one allowed network.

    Containment must be total: a /16 scan target is not permitted by a /24
    allowance, even though they overlap.
    """
    if isinstance(target, ipaddress.IPv4Address | ipaddress.IPv6Address):
        return any(target in network for network in allowed)
    return any(
        target.subnet_of(network) for network in allowed if network.version == target.version
    )


def assert_network_in_scope(value: str, allowed: list[IPNetwork]) -> IPNetwork:
    """Validate a CIDR/address target against the allowlist. Returns the parsed network."""
    network = parse_network(value)
    if not allowed:
        raise OutOfScope(
            "This engagement has no authorised ranges, so every target is out of scope. "
            "Add authorised CIDRs to the engagement first."
        )
    if not is_within(network, allowed):
        raise OutOfScope(
            f"{network} is not fully contained by any authorised range "
            f"({', '.join(str(n) for n in allowed)})"
        )
    return network


def assert_host_in_scope(
    value: str, allowed: list[IPNetwork], *, resolve: bool = True
) -> IPAddress | str:
    """Validate an address-or-hostname target against the allowlist.

    Hostnames are resolved and **every** resolved address must be in scope; a
    name that answers with even one out-of-scope address is rejected rather than
    partially allowed.
    """
    host = parse_host(value)
    if not allowed:
        raise OutOfScope(
            "This engagement has no authorised ranges, so every target is out of scope."
        )

    if isinstance(host, str):
        if not resolve:
            raise OutOfScope(
                f"Hostname {host!r} cannot be scope-checked without DNS resolution"
            )
        resolved = resolve_host(host)
        outside = [addr for addr in resolved if not is_within(addr, allowed)]
        if outside:
            raise OutOfScope(
                f"Hostname {host!r} resolves to {', '.join(str(a) for a in outside)}, "
                f"which is outside the authorised ranges"
            )
        return host

    if not is_within(host, allowed):
        raise OutOfScope(
            f"{host} is not inside any authorised range "
            f"({', '.join(str(n) for n in allowed)})"
        )
    return host


def _pre_validate(value: str) -> str:
    """Shared syntactic gate applied before any parsing attempt."""
    if not isinstance(value, str):
        raise TargetSyntaxError(f"Target must be a string, got {type(value).__name__}")

    candidate = value.strip()
    if not candidate:
        raise TargetSyntaxError("Target cannot be empty")
    if len(candidate) > MAX_TARGET_LENGTH:
        raise TargetSyntaxError(f"Target is longer than {MAX_TARGET_LENGTH} characters")
    if candidate.startswith("-"):
        # Belt and braces: ipaddress would reject this anyway, but a leading
        # dash is the exact shape of an argv-injection attempt and deserves its
        # own error rather than a generic parse failure.
        raise TargetSyntaxError(f"Target {value!r} may not start with '-'")
    if any(char.isspace() for char in candidate):
        raise TargetSyntaxError(f"Target {value!r} may not contain whitespace")
    return candidate
