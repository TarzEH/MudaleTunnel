"""API serializers.

Read serializers expose derived, display-ready fields so the dashboard does not
have to reimplement the model's vocabulary. Write serializers are deliberately
thin: they validate shape only, then hand off to ``apps.*.services``, which owns
scope checks, role checks and audit. Nothing here writes to the database
directly, so no endpoint can bypass the policy layer.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.agents.models import Agent
from apps.audit.models import AuditEvent
from apps.engagements.models import Engagement
from apps.engagements.scope import ScopeViolation, networks_from_strings
from apps.scans.models import Scan, Service
from apps.tunnels.models import Tunnel

# ── Accounts ────────────────────────────────────────────────────────────


class MeSerializer(serializers.Serializer):
    server_version = serializers.CharField()
    id = serializers.IntegerField()
    username = serializers.CharField()
    callsign = serializers.CharField()
    role = serializers.CharField()
    can_mutate = serializers.BooleanField()
    is_admin = serializers.BooleanField()


# ── Engagements ─────────────────────────────────────────────────────────


class EngagementSerializer(serializers.ModelSerializer):
    tunnel_count = serializers.IntegerField(read_only=True, default=0)
    scan_count = serializers.IntegerField(read_only=True, default=0)
    agent_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Engagement
        fields = [
            "id", "name", "slug", "client", "status", "authorized_cidrs",
            "starts_on", "ends_on", "notes", "created_at",
            "tunnel_count", "scan_count", "agent_count",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_authorized_cidrs(self, value: list[str]) -> list[str]:
        """Normalise the allowlist so what is stored is what is enforced.

        Rejecting the whole list on one bad entry is deliberate — a partially
        applied scope change is worse than a refused one.
        """
        try:
            networks = networks_from_strings(list(value or []))
        except ScopeViolation as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return [str(network) for network in networks]


# ── Agents ──────────────────────────────────────────────────────────────


class AgentSerializer(serializers.ModelSerializer):
    engine_display = serializers.CharField(source="get_engine_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Agent
        fields = [
            "id", "engagement", "engine", "engine_display", "name", "status",
            "status_display", "remote_host", "remote_port", "hostname",
            "operating_system", "architecture", "remote_username", "is_privileged",
            "reachable_cidrs", "engine_session_id", "last_seen_at", "created_at",
        ]
        read_only_fields = ["id", "created_at", "last_seen_at", "status"]


# ── Tunnels ─────────────────────────────────────────────────────────────


class TunnelSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    engagement_name = serializers.CharField(source="engagement.name", read_only=True)
    agent_name = serializers.CharField(source="agent.name", read_only=True, default=None)
    created_by_name = serializers.CharField(
        source="created_by.username", read_only=True, default=None
    )
    uptime_seconds = serializers.FloatField(read_only=True)
    description = serializers.SerializerMethodField()

    class Meta:
        model = Tunnel
        fields = [
            "id", "engagement", "engagement_name", "agent", "agent_name",
            "kind", "kind_display", "label", "description", "desired_state",
            "status", "spec", "pid", "last_error", "restart_count",
            "started_at", "stopped_at", "created_at", "created_by_name",
            "uptime_seconds",
        ]
        read_only_fields = fields

    def get_description(self, tunnel: Tunnel) -> str:
        """A one-line summary built from the validated spec.

        Falls back to the kind name rather than raising: a spec that no longer
        parses (because the schema tightened) must not make the whole list 500.
        """
        from apps.engine.adapters.ssh import SshAdapter
        from apps.engine.specs import SpecError, parse_spec

        try:
            spec = parse_spec(tunnel.kind, tunnel.spec)
        except SpecError:
            return tunnel.get_kind_display()

        try:
            adapter = SshAdapter("ssh")
            adapter._resolved = "ssh"  # description only; never executed
            return adapter.plan(spec).description
        except Exception:
            return tunnel.get_kind_display()


class TunnelCreateSerializer(serializers.Serializer):
    """Shape validation only — ``apps.tunnels.services.create_tunnel`` owns policy."""

    engagement = serializers.PrimaryKeyRelatedField(queryset=Engagement.objects.all())
    kind = serializers.ChoiceField(choices=Tunnel._meta.get_field("kind").choices)
    label = serializers.CharField(required=False, allow_blank=True, default="", max_length=128)
    spec = serializers.DictField()
    agent = serializers.PrimaryKeyRelatedField(
        queryset=Agent.objects.all(), required=False, allow_null=True
    )


class TunnelLogSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    level = serializers.CharField()
    message = serializers.CharField()
    source = serializers.CharField()


# ── Scans ───────────────────────────────────────────────────────────────


class ServiceSerializer(serializers.ModelSerializer):
    banner = serializers.CharField(read_only=True)
    target = serializers.CharField(source="scan.target", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id", "scan", "target", "host", "hostname", "port", "protocol",
            "state", "service_name", "product", "version", "extra_info", "banner",
        ]
        read_only_fields = fields


class ScanSerializer(serializers.ModelSerializer):
    profile_display = serializers.CharField(source="get_profile_display", read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.username", read_only=True, default=None
    )
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = Scan
        fields = [
            "id", "engagement", "target", "profile", "profile_display", "status",
            "via_tunnel", "hosts_up", "services_found", "error", "queued_at",
            "started_at", "finished_at", "duration_seconds", "requested_by_name",
        ]
        read_only_fields = fields


class ScanCreateSerializer(serializers.Serializer):
    engagement = serializers.PrimaryKeyRelatedField(queryset=Engagement.objects.all())
    # Intentionally a plain CharField: the real validation is the engagement's
    # scope check in the service layer, which parses it into a network object.
    target = serializers.CharField(max_length=253)
    profile = serializers.ChoiceField(choices=Scan._meta.get_field("profile").choices)
    via_tunnel = serializers.PrimaryKeyRelatedField(
        queryset=Tunnel.objects.all(), required=False, allow_null=True
    )


# ── Audit ───────────────────────────────────────────────────────────────


class AuditEventSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id", "created_at", "actor_label", "action", "action_display", "result",
            "engagement", "object_type", "object_id", "object_label", "message",
            "request_id", "source_ip",
        ]
        read_only_fields = fields
