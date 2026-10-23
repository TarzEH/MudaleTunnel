"""Tunnel, scan, and status enums — single source of truth.

Both Django models and the standalone CLI import from here.
Django TextChoices is a StrEnum subclass, so these values work
directly as model field choices.
"""

from __future__ import annotations

from enum import StrEnum


class TunnelKind(StrEnum):
    SSH_LOCAL = "ssh_local"
    SSH_DYNAMIC = "ssh_dynamic"
    SSH_REMOTE = "ssh_remote"
    SSH_REMOTE_DYNAMIC = "ssh_remote_dynamic"
    LIGOLO = "ligolo"


TUNNEL_KIND_LABELS: dict[str, str] = {
    TunnelKind.SSH_LOCAL: "SSH local forward",
    TunnelKind.SSH_DYNAMIC: "SSH SOCKS proxy",
    TunnelKind.SSH_REMOTE: "SSH reverse forward",
    TunnelKind.SSH_REMOTE_DYNAMIC: "SSH reverse SOCKS",
    TunnelKind.LIGOLO: "ligolo-ng TUN tunnel",
}


class ScanProfile(StrEnum):
    DISCOVERY = "discovery"
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"
    UDP_TOP = "udp_top"


SCAN_PROFILE_LABELS: dict[str, str] = {
    ScanProfile.DISCOVERY: "Host discovery (ping sweep)",
    ScanProfile.QUICK: "Quick (top 100 ports)",
    ScanProfile.STANDARD: "Standard (top 1000 + versions)",
    ScanProfile.FULL: "Full (all TCP ports + versions)",
    ScanProfile.UDP_TOP: "UDP (top 100 ports)",
}


class TunnelStatus(StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    ACTIVE = "active"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class DesiredState(StrEnum):
    UP = "up"
    DOWN = "down"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


LIVE_STATUSES = frozenset(
    {TunnelStatus.STARTING, TunnelStatus.ACTIVE, TunnelStatus.DEGRADED, TunnelStatus.STOPPING}
)
TERMINAL_STATUSES = frozenset({TunnelStatus.STOPPED, TunnelStatus.FAILED})
TERMINAL_SCAN_STATUSES = frozenset(
    {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED, ScanStatus.TIMED_OUT}
)
