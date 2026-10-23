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

Reachability — which subnets a pivot can actually see — is not modelled here.
It is *earned* by running a scan through the tunnel, and lives on
``Agent.reachable_cidrs`` and the scan results themselves.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from mudale_engine.enums import (
    LIVE_STATUSES,
    TUNNEL_KIND_LABELS,
    DesiredState,
    TunnelKind,
    TunnelStatus,
)

_TUNNEL_KIND_CHOICES = [(k.value, TUNNEL_KIND_LABELS[k]) for k in TunnelKind]
_DESIRED_STATE_CHOICES = [(s.value, s.value.title()) for s in DesiredState]
_TUNNEL_STATUS_CHOICES = [(s.value, s.value.title()) for s in TunnelStatus]


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
    kind = models.CharField(max_length=32, choices=_TUNNEL_KIND_CHOICES)
    label = models.CharField(max_length=128, blank=True)

    # ── Desired (written by the web tier) ───────────────────────────────
    desired_state = models.CharField(
        max_length=8, choices=_DESIRED_STATE_CHOICES, default=DesiredState.UP, db_index=True
    )
    # Engine-specific, schema-validated parameters. See mudale_engine.specs.
    spec = models.JSONField(default=dict)

    # ── Observed (written by the engine daemon only) ────────────────────
    status = models.CharField(
        max_length=16, choices=_TUNNEL_STATUS_CHOICES, default=TunnelStatus.PENDING, db_index=True
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
