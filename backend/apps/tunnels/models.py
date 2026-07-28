"""Tunnels, routes and listeners.

**Desired state vs observed state.** The web tier never spawns a process. It
writes what the operator *wants* (``desired_state``) and the engine daemon
reconciles reality towards it, reporting back what *is* (``status``). That split
is what makes the control plane survivable: Django can restart, be redeployed or
crash without touching a live tunnel, and the engine can restart and re-adopt
what it finds instead of orphaning it.

``spec`` holds the engine-specific parameters as validated JSON rather than as a
command string. Nothing in this module is ever concatenated into a shell — the
adapters build argv lists from these typed fields.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

PORT_VALIDATORS = [MinValueValidator(1), MaxValueValidator(65535)]


class TunnelKind(models.TextChoices):
    # SSH local forward: -L local_port:target_host:target_port
    SSH_LOCAL = "ssh_local", "SSH local forward"
    # SSH dynamic forward (SOCKS): -D local_port
    SSH_DYNAMIC = "ssh_dynamic", "SSH SOCKS proxy"
    # SSH remote forward: -R bind:remote_port:target_host:target_port
    SSH_REMOTE = "ssh_remote", "SSH reverse forward"
    # SSH remote dynamic (reverse SOCKS, OpenSSH 7.6+): -R bind:port
    SSH_REMOTE_DYNAMIC = "ssh_remote_dynamic", "SSH reverse SOCKS"
    # ligolo-ng TUN interface bound to an agent session
    LIGOLO_TUN = "ligolo_tun", "ligolo-ng tunnel"


class DesiredState(models.TextChoices):
    UP = "up", "Up"
    DOWN = "down", "Down"


class TunnelStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    STARTING = "starting", "Starting"
    ACTIVE = "active", "Active"
    # Process alive but a health check is failing (port not listening, etc).
    DEGRADED = "degraded", "Degraded"
    STOPPING = "stopping", "Stopping"
    STOPPED = "stopped", "Stopped"
    FAILED = "failed", "Failed"


#: Statuses from which the engine considers the tunnel to be occupying a process.
LIVE_STATUSES = frozenset(
    {TunnelStatus.STARTING, TunnelStatus.ACTIVE, TunnelStatus.DEGRADED, TunnelStatus.STOPPING}
)

#: Statuses after which no further transition is expected without operator action.
TERMINAL_STATUSES = frozenset({TunnelStatus.STOPPED, TunnelStatus.FAILED})


class TunnelQuerySet(models.QuerySet):
    def live(self) -> TunnelQuerySet:
        return self.filter(status__in=LIVE_STATUSES)

    def needing_reconciliation(self) -> TunnelQuerySet:
        """Rows where observed state does not match desired state."""
        return self.filter(
            models.Q(desired_state=DesiredState.UP, status__in=[TunnelStatus.PENDING])
            | models.Q(desired_state=DesiredState.DOWN, status__in=LIVE_STATUSES)
        )


class Tunnel(models.Model):
    engagement = models.ForeignKey(
        "engagements.Engagement", on_delete=models.CASCADE, related_name="tunnels"
    )
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.CASCADE,
        related_name="tunnels",
        null=True,
        blank=True,
        help_text="The foothold this tunnel runs through. Null for a direct SSH tunnel.",
    )
    kind = models.CharField(max_length=32, choices=TunnelKind.choices)
    label = models.CharField(max_length=128, blank=True)

    # ── Desired (written by the web tier) ───────────────────────────────
    desired_state = models.CharField(
        max_length=8, choices=DesiredState.choices, default=DesiredState.UP, db_index=True
    )
    # Engine-specific, schema-validated parameters. See apps.engine.specs.
    spec = models.JSONField(default=dict)

    # ── Observed (written by the engine daemon only) ────────────────────
    status = models.CharField(
        max_length=16, choices=TunnelStatus.choices, default=TunnelStatus.PENDING, db_index=True
    )
    # PID of the process the engine actually supervises. Because no adapter uses
    # a self-backgrounding flag (ssh -f and friends), this PID stays valid for
    # the tunnel's whole life and is safe to signal.
    pid = models.IntegerField(null=True, blank=True)
    # Identifies the engine instance that owns the process, so a second daemon
    # does not adopt or kill a tunnel it did not start.
    owner_engine_id = models.CharField(max_length=64, blank=True, db_index=True)

    last_error = models.TextField(blank=True)
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    restart_count = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tunnels_created",
    )

    objects = TunnelQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["engagement", "status"]),
            models.Index(fields=["desired_state", "status"]),
        ]

    def __str__(self) -> str:
        return self.label or f"{self.get_kind_display()} #{self.pk}"

    @property
    def is_live(self) -> bool:
        return self.status in LIVE_STATUSES

    @property
    def uptime_seconds(self) -> float | None:
        if not self.started_at:
            return None
        from django.utils import timezone

        end = self.stopped_at or timezone.now()
        return (end - self.started_at).total_seconds()


class Route(models.Model):
    """A subnet routed through an agent's tunnel interface.

    ligolo-ng's model: an interface exists, and CIDRs are attached to it so the
    operator's OS sends matching traffic into the tunnel.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        REMOVING = "removing", "Removing"
        REMOVED = "removed", "Removed"
        FAILED = "failed", "Failed"

    tunnel = models.ForeignKey(Tunnel, on_delete=models.CASCADE, related_name="routes")
    cidr = models.CharField(max_length=64)
    interface_name = models.CharField(max_length=64, blank=True)

    desired_state = models.CharField(
        max_length=8, choices=DesiredState.choices, default=DesiredState.UP
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    last_error = models.TextField(blank=True)

    # True when the route came from ligolo's autoroute rather than an operator.
    discovered = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="routes_created",
    )

    class Meta:
        ordering = ["tunnel", "cidr"]
        constraints = [
            models.UniqueConstraint(fields=["tunnel", "cidr"], name="unique_cidr_per_tunnel")
        ]

    def __str__(self) -> str:
        return f"{self.cidr} via {self.tunnel}"


class Listener(models.Model):
    """A port bound on the agent side, relayed back through the tunnel.

    ligolo-ng's ``listener_add``; the equivalent of Cobalt Strike's ``rportfwd``.
    """

    class Protocol(models.TextChoices):
        TCP = "tcp", "TCP"
        UDP = "udp", "UDP"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        STOPPING = "stopping", "Stopping"
        STOPPED = "stopped", "Stopped"
        FAILED = "failed", "Failed"

    tunnel = models.ForeignKey(Tunnel, on_delete=models.CASCADE, related_name="listeners")
    label = models.CharField(max_length=128, blank=True)

    # Loopback by default. Exposing a listener on every interface of a host
    # inside a client network is a deliberate act, so widening it has to be an
    # explicit choice rather than something an operator gets by accident.
    bind_host = models.CharField(max_length=253, default="127.0.0.1")
    bind_port = models.PositiveIntegerField(validators=PORT_VALIDATORS)
    to_host = models.CharField(max_length=253)
    to_port = models.PositiveIntegerField(validators=PORT_VALIDATORS)
    protocol = models.CharField(max_length=8, choices=Protocol.choices, default=Protocol.TCP)

    desired_state = models.CharField(
        max_length=8, choices=DesiredState.choices, default=DesiredState.UP
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    engine_listener_id = models.CharField(max_length=128, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listeners_created",
    )

    class Meta:
        ordering = ["tunnel", "bind_port"]
        constraints = [
            models.UniqueConstraint(
                fields=["tunnel", "bind_host", "bind_port", "protocol"],
                name="unique_bind_per_tunnel",
            )
        ]

    def __str__(self) -> str:
        return f"{self.bind_host}:{self.bind_port} → {self.to_host}:{self.to_port}/{self.protocol}"


class TunnelLogLevel(models.TextChoices):
    DEBUG = "debug", "Debug"
    INFO = "info", "Info"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class TunnelLog(models.Model):
    """Engine-side log lines for a tunnel, streamed to the dashboard.

    Retained per-tunnel and pruned by the engine so a chatty process cannot fill
    the database.
    """

    tunnel = models.ForeignKey(Tunnel, on_delete=models.CASCADE, related_name="logs")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(
        max_length=8, choices=TunnelLogLevel.choices, default=TunnelLogLevel.INFO
    )
    message = models.TextField()
    # "stderr", "stdout", "engine" — where the line came from.
    source = models.CharField(max_length=16, default="engine")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tunnel", "-created_at"])]

    def __str__(self) -> str:
        return f"[{self.level}] {self.message[:80]}"
