"""Agents — a foothold the control plane can route traffic through.

An agent is whatever the far end of a tunnel is: a ligolo-ng agent process on a
compromised host, or an SSH server we hold credentials for. Modelling both as
"agent" keeps the dashboard, the audit trail and the topology graph engine-
agnostic, and lets a single engagement mix engines.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class EngineKind(models.TextChoices):
    SSH = "ssh", "SSH"
    LIGOLO = "ligolo", "ligolo-ng"


class AgentStatus(models.TextChoices):
    # Registered but never seen — e.g. a ligolo agent binary generated and
    # staged, but not yet executed on the target.
    PENDING = "pending", "Pending"
    ONLINE = "online", "Online"
    OFFLINE = "offline", "Offline"
    # Deliberately retired by an operator; the engine will not reconnect.
    RETIRED = "retired", "Retired"


class AgentQuerySet(models.QuerySet):
    def online(self) -> AgentQuerySet:
        return self.filter(status=AgentStatus.ONLINE)

    def usable(self) -> AgentQuerySet:
        """Agents the engine may start new tunnels through."""
        return self.exclude(status=AgentStatus.RETIRED)


class Agent(models.Model):
    engagement = models.ForeignKey(
        "engagements.Engagement", on_delete=models.CASCADE, related_name="agents"
    )
    engine = models.CharField(max_length=16, choices=EngineKind.choices)
    name = models.CharField(max_length=128, help_text="Operator-facing label, e.g. 'dmz-jump'")

    status = models.CharField(
        max_length=16, choices=AgentStatus.choices, default=AgentStatus.PENDING, db_index=True
    )

    # ── Where it is ─────────────────────────────────────────────────────
    # Address the control plane reaches the agent at (SSH host, or the source
    # address a ligolo agent called back from).
    remote_host = models.CharField(max_length=253, blank=True)
    remote_port = models.PositiveIntegerField(null=True, blank=True)

    # ── What it is (reported by the agent, so treated as untrusted display
    #    data — never interpolated into a command line) ──────────────────
    hostname = models.CharField(max_length=253, blank=True)
    operating_system = models.CharField(max_length=64, blank=True)
    architecture = models.CharField(max_length=32, blank=True)
    remote_username = models.CharField(max_length=128, blank=True)
    is_privileged = models.BooleanField(null=True, blank=True)

    # ligolo-ng's own session identifier, so the engine can address the right
    # session when the proxy holds several.
    engine_session_id = models.CharField(max_length=128, blank=True, db_index=True)

    # Subnets this agent can see, as reported by the agent or discovered by
    # autoroute. Feeds the topology graph and the pivot-path search.
    reachable_cidrs = models.JSONField(default=list, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agents_created",
    )

    objects = AgentQuerySet.as_manager()

    class Meta:
        ordering = ["engagement", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["engagement", "name"], name="unique_agent_name_per_engagement"
            )
        ]
        indexes = [models.Index(fields=["engagement", "status"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_engine_display()})"

    @property
    def is_reachable(self) -> bool:
        return self.status == AgentStatus.ONLINE

    def mark_seen(self, *, status: str = AgentStatus.ONLINE) -> None:
        now = timezone.now()
        fields = ["status", "last_seen_at", "updated_at"]
        self.status = status
        self.last_seen_at = now
        if self.first_seen_at is None:
            self.first_seen_at = now
            fields.append("first_seen_at")
        self.save(update_fields=fields)
