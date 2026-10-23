"""Pivoting, driven by what nmap actually found.

ligolo-ng's approach is to build a TUN interface and route whole subnets into
it, so every tool works unmodified. That needs a custom agent, a userland TCP/IP
stack, and root on the operator's machine.

This takes the same goal — reach things behind a foothold without hand-rolling a
forward for each one — and gets there from the other end. Instead of routing a
subnet you *hope* is there, you scan through the pivot, and then act on what is
provably reachable:

1. **Reach** — a SOCKS proxy through the foothold (``ssh -D``).
2. **Discover** — run nmap *through* that proxy. Every open port it finds is a
   host the pivot can genuinely reach, recorded with the tunnel it was seen
   through.
3. **Expose** — turn any discovered service into a direct local forward
   (``ssh -L``), so tools that cannot speak SOCKS get a plain localhost port.
4. **Chain** — a newly reachable host can itself become the next foothold.

The trade-off against a TUN interface is honest: SOCKS is TCP-only and needs
either a SOCKS-aware tool or proxychains. What you get in exchange is that no
custom agent has to be dropped on the target, nothing needs root, and the map is
evidence rather than assumption.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field

from django.db import transaction

from apps.agents.models import Agent
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.engagements.models import Engagement
from apps.scans.models import Scan, Service
from apps.tunnels.models import DesiredState, Tunnel, TunnelKind, TunnelStatus

logger = logging.getLogger(__name__)

#: Ports we will not silently auto-expose. Forwarding these is legitimate, but
#: it should be a decision an operator makes explicitly rather than something
#: `pivot auto` does to every host it can see.
SENSITIVE_PORTS = frozenset({22, 3389, 5985, 5986, 623})

#: Where auto-allocated local forwards start. Below 1024 needs root, and the
#: ephemeral range is where the OS hands out source ports.
AUTO_PORT_START = 14000
AUTO_PORT_END = 14999


class PivotError(Exception):
    """A pivot operation cannot be carried out as asked."""


@dataclass
class ReachableHost:
    """One host proven reachable, and through what."""

    host: str
    via_tunnel_id: int | None
    via_label: str
    open_ports: list[int] = field(default_factory=list)
    hostname: str = ""

    @property
    def is_direct(self) -> bool:
        return self.via_tunnel_id is None


@dataclass
class PivotMap:
    """The engagement's reachability, as evidenced by scans."""

    direct: list[ReachableHost] = field(default_factory=list)
    by_tunnel: dict[int, list[ReachableHost]] = field(default_factory=dict)
    subnets_by_tunnel: dict[int, list[str]] = field(default_factory=dict)

    @property
    def total_hosts(self) -> int:
        return len(self.direct) + sum(len(hosts) for hosts in self.by_tunnel.values())


# ── Reachability ────────────────────────────────────────────────────────


def build_map(engagement: Engagement) -> PivotMap:
    """Assemble what is reachable, and through which pivot.

    Derived entirely from completed scans: a host appears here because nmap
    reached it, not because someone declared a route.
    """
    pivot_map = PivotMap()
    grouped: dict[int | None, dict[str, ReachableHost]] = {}

    services = (
        Service.objects.filter(engagement=engagement, state=Service.State.OPEN)
        .select_related("scan", "scan__via_tunnel")
        .order_by("host", "port")
    )

    for service in services:
        tunnel = service.scan.via_tunnel
        key = tunnel.pk if tunnel else None
        bucket = grouped.setdefault(key, {})

        entry = bucket.get(service.host)
        if entry is None:
            entry = ReachableHost(
                host=service.host,
                via_tunnel_id=key,
                via_label=str(tunnel) if tunnel else "direct",
                hostname=service.hostname,
            )
            bucket[service.host] = entry
        if service.port not in entry.open_ports:
            entry.open_ports.append(service.port)

    for key, hosts in grouped.items():
        ordered = sorted(hosts.values(), key=lambda h: ipaddress.ip_address(h.host))
        if key is None:
            pivot_map.direct = ordered
        else:
            pivot_map.by_tunnel[key] = ordered
            pivot_map.subnets_by_tunnel[key] = summarise_subnets(h.host for h in ordered)

    return pivot_map


def summarise_subnets(hosts) -> list[str]:
    """Collapse individual addresses into the /24s (or /64s) they fall in.

    A rough summary on purpose. Its job is to answer "what part of the network
    does this pivot open up", not to be an authoritative route table.
    """
    networks: set[str] = set()
    for host in hosts:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            continue
        prefix = 24 if address.version == 4 else 64
        networks.add(str(ipaddress.ip_network(f"{address}/{prefix}", strict=False)))
    return sorted(networks)


def refresh_agent_reachability(scan: Scan) -> list[str]:
    """After a tunnelled scan, record what its foothold can see.

    Called by the scan ingest path. Returns the updated CIDR list.
    """
    tunnel = scan.via_tunnel
    if tunnel is None or tunnel.agent_id is None:
        return []

    hosts = (
        Service.objects.filter(scan=scan, state=Service.State.OPEN)
        .values_list("host", flat=True)
        .distinct()
    )
    discovered = summarise_subnets(hosts)
    if not discovered:
        return []

    agent = Agent.objects.filter(pk=tunnel.agent_id).first()
    if agent is None:
        return []

    merged = sorted(set(agent.reachable_cidrs or []) | set(discovered))
    if merged != list(agent.reachable_cidrs or []):
        agent.reachable_cidrs = merged
        agent.save(update_fields=["reachable_cidrs", "updated_at"])
    return merged


# ── Exposing a discovered service ───────────────────────────────────────


def allocate_local_port(engagement: Engagement) -> int:
    """Pick a free local port for an auto-created forward.

    "Free" means not already claimed by another tunnel in this control plane.
    The engine still finds out for certain when ssh tries to bind — and because
    ``ExitOnForwardFailure`` is set, a collision surfaces as a failed tunnel
    with a real error rather than a tunnel that silently forwards nothing.
    """
    taken = set()
    for tunnel in Tunnel.objects.filter(engagement=engagement).exclude(
        status__in=[TunnelStatus.STOPPED, TunnelStatus.FAILED]
    ):
        port = tunnel.spec.get("local_port")
        if isinstance(port, int):
            taken.add(port)

    for candidate in range(AUTO_PORT_START, AUTO_PORT_END + 1):
        if candidate not in taken:
            return candidate
    raise PivotError(
        f"No free local port between {AUTO_PORT_START} and {AUTO_PORT_END}. "
        f"Stop some tunnels first."
    )


def expose_service(
    service: Service,
    *,
    operator=None,
    local_port: int | None = None,
    label: str = "",
) -> Tunnel:
    """Create a local forward to a discovered service, through the pivot it was found on.

    This is the payoff of scanning through a tunnel: nmap says 10.4.9.5:1433 is
    reachable from the jump host, and this turns that into 127.0.0.1:14000 with
    no manual ssh invocation.
    """
    from apps.tunnels import services as tunnel_services

    pivot = service.scan.via_tunnel
    if pivot is None:
        raise PivotError(
            f"{service.host}:{service.port} was found by a direct scan, so it is already "
            f"reachable without a tunnel."
        )

    if pivot.kind != TunnelKind.SSH_DYNAMIC:
        raise PivotError(
            f"Tunnel {pivot.pk} is a {pivot.get_kind_display()}, not a SOCKS proxy. "
            f"Services can only be exposed through the pivot they were discovered on."
        )

    endpoint = dict(pivot.spec.get("endpoint") or {})
    if not endpoint:
        raise PivotError(f"Tunnel {pivot.pk} has no usable SSH endpoint in its spec.")

    port = local_port or allocate_local_port(service.engagement)

    return tunnel_services.create_tunnel(
        engagement=service.engagement,
        kind=TunnelKind.SSH_LOCAL,
        spec={
            "endpoint": endpoint,
            "local_bind": "127.0.0.1",
            "local_port": port,
            "target_host": service.host,
            "target_port": service.port,
        },
        operator=operator,
        agent=pivot.agent,
        label=label or f"{service.service_name or 'service'} on {service.host}",
    )


@transaction.atomic
def auto_expose(
    engagement: Engagement,
    *,
    tunnel: Tunnel,
    operator=None,
    ports: list[int] | None = None,
    include_sensitive: bool = False,
    limit: int = 20,
) -> list[Tunnel]:
    """Expose everything interesting a pivot found, in one go.

    Bounded and explicit by design: administrative ports are skipped unless
    asked for, and the number of forwards is capped, because "open a hundred
    ports into a client network" should never be the accidental outcome of one
    command.
    """
    queryset = Service.objects.filter(
        engagement=engagement, scan__via_tunnel=tunnel, state=Service.State.OPEN
    ).order_by("host", "port")

    if ports:
        queryset = queryset.filter(port__in=ports)

    created: list[Tunnel] = []
    seen: set[tuple[str, int]] = set()

    for service in queryset:
        if len(created) >= limit:
            logger.info("auto_expose stopped at the limit of %d forwards", limit)
            break
        if (service.host, service.port) in seen:
            continue
        if service.port in SENSITIVE_PORTS and not include_sensitive:
            continue
        seen.add((service.host, service.port))

        if _already_exposed(engagement, service):
            continue

        created.append(expose_service(service, operator=operator))

    record(
        AuditAction.TUNNEL_REQUESTED,
        engagement=engagement,
        obj=tunnel,
        message=f"Auto-exposed {len(created)} services discovered through this pivot",
        payload={"count": len(created), "skipped_sensitive": not include_sensitive},
    )
    return created


def _already_exposed(engagement: Engagement, service: Service) -> bool:
    """Whether a live forward to this host and port already exists."""
    return Tunnel.objects.filter(
        engagement=engagement,
        kind=TunnelKind.SSH_LOCAL,
        desired_state=DesiredState.UP,
        spec__target_host=service.host,
        spec__target_port=service.port,
    ).exists()


# ── Client configuration ────────────────────────────────────────────────


def proxychains_config(tunnel: Tunnel) -> str:
    """A ready-to-use proxychains config for a SOCKS pivot.

    SOCKS is only useful if your tools point at it, and hand-writing this file
    is the step everyone gets wrong.
    """
    if tunnel.kind != TunnelKind.SSH_DYNAMIC:
        raise PivotError(
            f"Tunnel {tunnel.pk} is a {tunnel.get_kind_display()}, not a SOCKS proxy."
        )

    bind = tunnel.spec.get("local_bind", "127.0.0.1")
    port = tunnel.spec.get("local_port")

    safe_label = str(tunnel).replace("\n", " ").replace("\r", " ")
    return "\n".join(
        [
            f"# proxychains config for MudaleTunnel pivot #{tunnel.pk} ({safe_label})",
            "#",
            "#   proxychains4 -f this-file nmap -sT -Pn 10.4.50.0/24",
            "#",
            "# -sT and -Pn matter: a SOCKS proxy carries TCP connections, so a SYN",
            "# scan cannot work and nmap's host discovery has nothing to probe with.",
            "",
            "strict_chain",
            "proxy_dns",
            "remote_dns_subnet 224",
            "tcp_read_time_out 15000",
            "tcp_connect_time_out 8000",
            "",
            "[ProxyList]",
            f"socks5 {bind} {port}",
            "",
        ]
    )
