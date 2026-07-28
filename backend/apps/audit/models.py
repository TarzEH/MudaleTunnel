"""Append-only audit trail.

A red-team tool has to be able to answer "who opened that tunnel into the client
network, and when" months after the fact. That answer must survive the operator
account being deleted and must not be editable from the application, so:

* ``actor_label`` denormalises the operator's identity at write time;
* :meth:`AuditEvent.save` refuses updates;
* :meth:`AuditEvent.delete` refuses deletion.

Retention/rotation is a deliberate out-of-band operation (a DBA task), not
something the application can be tricked into doing.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    # Authentication
    LOGIN = "auth.login", "Operator logged in"
    LOGIN_FAILED = "auth.login_failed", "Login failed"
    LOGOUT = "auth.logout", "Operator logged out"
    API_KEY_ISSUED = "auth.api_key_issued", "API key issued"
    API_KEY_REVOKED = "auth.api_key_revoked", "API key revoked"

    # Engagements
    ENGAGEMENT_CREATED = "engagement.created", "Engagement created"
    ENGAGEMENT_UPDATED = "engagement.updated", "Engagement updated"
    ENGAGEMENT_SCOPE_CHANGED = "engagement.scope_changed", "Engagement scope changed"

    # Agents
    AGENT_REGISTERED = "agent.registered", "Agent registered"
    AGENT_CONNECTED = "agent.connected", "Agent connected"
    AGENT_DISCONNECTED = "agent.disconnected", "Agent disconnected"
    AGENT_KILLED = "agent.killed", "Agent killed"

    # Tunnels and routing
    TUNNEL_REQUESTED = "tunnel.requested", "Tunnel requested"
    TUNNEL_STARTED = "tunnel.started", "Tunnel started"
    TUNNEL_STOPPED = "tunnel.stopped", "Tunnel stopped"
    TUNNEL_FAILED = "tunnel.failed", "Tunnel failed"
    ROUTE_ADDED = "route.added", "Route added"
    ROUTE_REMOVED = "route.removed", "Route removed"
    LISTENER_ADDED = "listener.added", "Listener added"
    LISTENER_REMOVED = "listener.removed", "Listener removed"

    # Scanning
    SCAN_REQUESTED = "scan.requested", "Scan requested"
    SCAN_COMPLETED = "scan.completed", "Scan completed"
    SCAN_FAILED = "scan.failed", "Scan failed"

    # Policy
    SCOPE_DENIED = "policy.scope_denied", "Action denied — out of scope"
    PERMISSION_DENIED = "policy.permission_denied", "Action denied — insufficient role"


class AuditResult(models.TextChoices):
    OK = "ok", "Succeeded"
    DENIED = "denied", "Denied"
    ERROR = "error", "Errored"


class AppendOnlyError(Exception):
    """Raised on any attempt to modify or delete an existing audit event."""


class AuditEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    # Survives actor deletion. "system" for engine-daemon actions.
    actor_label = models.CharField(max_length=128)

    action = models.CharField(max_length=64, choices=AuditAction.choices, db_index=True)
    result = models.CharField(max_length=16, choices=AuditResult.choices, default=AuditResult.OK)

    engagement = models.ForeignKey(
        "engagements.Engagement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    # Loose reference rather than a GenericForeignKey: the target row may be
    # deleted, and the audit entry must outlive it.
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_label = models.CharField(max_length=256, blank=True)

    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    request_id = models.CharField(max_length=36, blank=True, db_index=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["engagement", "-created_at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]
        verbose_name = "audit event"

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.actor_label} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError("Audit events are append-only and cannot be modified")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit events are append-only and cannot be deleted")
