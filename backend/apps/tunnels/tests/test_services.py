"""Tunnel service-layer tests — the policy choke point."""

from __future__ import annotations

import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEvent, AuditResult
from apps.engagements.scope import OutOfScope, ScopeViolation
from apps.engine.specs import SpecError
from apps.tunnels import services
from apps.tunnels.models import DesiredState, Tunnel, TunnelKind, TunnelStatus

pytestmark = pytest.mark.django_db


def local_spec(**overrides) -> dict:
    spec = {
        "endpoint": {"user": "opsec", "host": "10.4.0.10", "port": 22},
        "local_port": 8080,
        "target_host": "10.4.9.5",
        "target_port": 1433,
    }
    spec.update(overrides)
    return spec


# ── Creation ────────────────────────────────────────────────────────────


def test_tunnel_is_created_in_pending_state(engagement, operator):
    tunnel = services.create_tunnel(
        engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
    )
    assert tunnel.status == TunnelStatus.PENDING
    assert tunnel.desired_state == DesiredState.UP
    assert tunnel.pid is None, "the web tier must not start anything"


def test_spec_is_normalised_on_save(engagement, operator):
    """What is stored is the validated spec, not the caller's raw dict."""
    tunnel = services.create_tunnel(
        engagement=engagement,
        kind=TunnelKind.SSH_LOCAL,
        spec=local_spec(endpoint={"user": "opsec", "host": "10.4.0.10"}),
        operator=operator,
    )
    assert tunnel.spec["endpoint"]["port"] == 22
    assert tunnel.spec["local_bind"] == "127.0.0.1"


def test_creation_is_audited(engagement, operator):
    tunnel = services.create_tunnel(
        engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
    )
    event = AuditEvent.objects.filter(action=AuditAction.TUNNEL_REQUESTED).first()
    assert event.object_id == str(tunnel.pk)
    assert event.result == AuditResult.OK


# ── Scope enforcement ───────────────────────────────────────────────────


def test_out_of_scope_target_is_refused(engagement, operator):
    with pytest.raises(OutOfScope):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(target_host="8.8.8.8"),
            operator=operator,
        )
    assert Tunnel.objects.count() == 0


def test_out_of_scope_ssh_host_is_refused(engagement, operator):
    with pytest.raises(OutOfScope):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(endpoint={"user": "opsec", "host": "203.0.113.9"}),
            operator=operator,
        )


def test_denial_is_audited_before_it_raises(engagement, operator):
    """A blocked attempt is the entry a post-incident review most needs."""
    with pytest.raises(OutOfScope):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(target_host="8.8.8.8"),
            operator=operator,
        )
    event = AuditEvent.objects.filter(action=AuditAction.SCOPE_DENIED).first()
    assert event is not None
    assert event.result == AuditResult.DENIED
    assert "8.8.8.8" in event.message


def test_paused_engagement_refuses_new_tunnels(engagement, operator):
    from apps.engagements.models import EngagementStatus

    engagement.status = EngagementStatus.PAUSED
    engagement.save(update_fields=["status"])
    with pytest.raises(ScopeViolation, match="not operational"):
        services.create_tunnel(
            engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
        )


def test_local_bind_is_not_scope_checked(engagement, operator):
    """127.0.0.1 on the operator's own box is not 'touching' the client."""
    tunnel = services.create_tunnel(
        engagement=engagement,
        kind=TunnelKind.SSH_LOCAL,
        spec=local_spec(local_bind="127.0.0.1"),
        operator=operator,
    )
    assert tunnel.spec["local_bind"] == "127.0.0.1"


# ── Spec validation ─────────────────────────────────────────────────────


def test_malformed_spec_is_refused(engagement, operator):
    with pytest.raises(SpecError):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec={"endpoint": {"user": "opsec", "host": "10.4.0.10"}},  # missing ports
            operator=operator,
        )


def test_unknown_extra_field_is_refused(engagement, operator):
    """extra='forbid' means a typo cannot silently disable a constraint."""
    with pytest.raises(SpecError):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(smuggled="--evil"),
            operator=operator,
        )


def test_flag_shaped_ssh_user_is_refused(engagement, operator):
    with pytest.raises(SpecError):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(endpoint={"user": "-oProxyCommand=id", "host": "10.4.0.10"}),
            operator=operator,
        )


def test_out_of_range_port_is_refused(engagement, operator):
    with pytest.raises(SpecError):
        services.create_tunnel(
            engagement=engagement,
            kind=TunnelKind.SSH_LOCAL,
            spec=local_spec(local_port=99999),
            operator=operator,
        )


# ── Roles ───────────────────────────────────────────────────────────────


def test_viewer_cannot_create_a_tunnel(engagement, django_user_model):
    viewer = django_user_model.objects.create_user(
        username="viewer", password="x" * 16, role=Role.VIEWER
    )
    with pytest.raises(services.PermissionDenied):
        services.create_tunnel(
            engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=viewer
        )


def test_viewer_cannot_stop_a_tunnel(engagement, operator, django_user_model):
    tunnel = services.create_tunnel(
        engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
    )
    viewer = django_user_model.objects.create_user(
        username="viewer", password="x" * 16, role=Role.VIEWER
    )
    with pytest.raises(services.PermissionDenied):
        services.request_stop(tunnel, operator=viewer)


# ── Stop and restart ────────────────────────────────────────────────────


def test_stop_sets_desired_state_only(engagement, operator):
    """The web tier records intent; only the daemon may declare it stopped."""
    tunnel = services.create_tunnel(
        engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
    )
    tunnel.status = TunnelStatus.ACTIVE
    tunnel.save(update_fields=["status"])

    services.request_stop(tunnel, operator=operator)
    tunnel.refresh_from_db()

    assert tunnel.desired_state == DesiredState.DOWN
    assert tunnel.status == TunnelStatus.ACTIVE, "status is the engine's to change"


def test_restart_rechecks_scope_against_the_current_engagement(engagement, operator):
    """An engagement narrowed after creation must block the restart."""
    tunnel = services.create_tunnel(
        engagement=engagement, kind=TunnelKind.SSH_LOCAL, spec=local_spec(), operator=operator
    )
    engagement.authorized_cidrs = ["192.168.50.0/24"]
    engagement.save(update_fields=["authorized_cidrs"])

    with pytest.raises(OutOfScope):
        services.request_start(tunnel, operator=operator)


