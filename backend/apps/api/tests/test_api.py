"""End-to-end API tests over HTTP."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEvent
from apps.engagements.models import Engagement, EngagementMembership, EngagementStatus
from apps.tunnels.models import DesiredState, Tunnel, TunnelKind, TunnelStatus

pytestmark = pytest.mark.django_db


def spec() -> dict:
    return {
        "endpoint": {"user": "opsec", "host": "10.4.0.10", "port": 22},
        "local_port": 8080,
        "target_host": "10.4.9.5",
        "target_port": 1433,
    }


@pytest.fixture
def client(operator, engagement):
    EngagementMembership.objects.create(engagement=engagement, operator=operator)
    api = APIClient()
    api.force_authenticate(user=operator)
    return api


# ── Authentication ──────────────────────────────────────────────────────


def test_every_collection_requires_authentication():
    anon = APIClient()
    for name in ["engagement", "tunnel", "scan", "agent", "audit", "service"]:
        response = anon.get(reverse(f"v1:{name}-list"))
        assert response.status_code in (401, 403), f"{name} was readable anonymously"


def test_login_and_me(operator):
    api = APIClient()
    response = api.post(
        reverse("v1:login"), {"username": "opsec", "password": "correct-horse-battery"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "opsec"

    me = api.get(reverse("v1:me"))
    assert me.status_code == 200
    assert me.json()["can_mutate"] is True


def test_failed_login_is_audited():
    APIClient().post(reverse("v1:login"), {"username": "opsec", "password": "wrong"})
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).exists()


def test_failed_login_does_not_record_the_password():
    APIClient().post(reverse("v1:login"), {"username": "opsec", "password": "hunter2-secret"})
    event = AuditEvent.objects.get(action=AuditAction.LOGIN_FAILED)
    assert "hunter2-secret" not in str(event.payload)
    assert "hunter2-secret" not in event.message


# ── Cross-engagement isolation ──────────────────────────────────────────


def test_operator_cannot_see_another_teams_engagement(client, django_user_model):
    other_owner = django_user_model.objects.create_user(username="other", password="x" * 16)
    Engagement.objects.create(
        name="Someone else", slug="someone-else", status=EngagementStatus.ACTIVE,
        authorized_cidrs=["10.9.0.0/16"], created_by=other_owner,
    )
    results = client.get(reverse("v1:engagement-list")).json()["results"]
    assert [e["slug"] for e in results] == ["acme-internal"]


def test_operator_cannot_create_a_tunnel_in_a_foreign_engagement(client, django_user_model):
    other_owner = django_user_model.objects.create_user(username="other", password="x" * 16)
    foreign = Engagement.objects.create(
        name="Foreign", slug="foreign", status=EngagementStatus.ACTIVE,
        authorized_cidrs=["10.4.0.0/16"], created_by=other_owner,
    )
    response = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": foreign.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    )
    assert response.status_code == 403
    assert Tunnel.objects.count() == 0


def test_tunnel_from_another_engagement_is_not_visible(client, django_user_model, engagement):
    other_owner = django_user_model.objects.create_user(username="other", password="x" * 16)
    foreign = Engagement.objects.create(
        name="Foreign", slug="foreign", status=EngagementStatus.ACTIVE,
        authorized_cidrs=["10.4.0.0/16"], created_by=other_owner,
    )
    hidden = Tunnel.objects.create(
        engagement=foreign, kind=TunnelKind.SSH_LOCAL, spec=spec()
    )
    assert client.get(reverse("v1:tunnel-list")).json()["count"] == 0
    assert client.get(reverse("v1:tunnel-detail", args=[hidden.pk])).status_code == 404


# ── Tunnel lifecycle ────────────────────────────────────────────────────


def test_create_tunnel(client, engagement):
    response = client.post(
        reverse("v1:tunnel-list"),
        {
            "engagement": engagement.pk,
            "kind": TunnelKind.SSH_LOCAL,
            "label": "sql via jump",
            "spec": spec(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == TunnelStatus.PENDING
    assert body["desired_state"] == DesiredState.UP
    assert body["pid"] is None
    assert "10.4.9.5:1433" in body["description"]


def test_out_of_scope_target_returns_a_useful_message(client, engagement):
    """The refusal text is a safety feature — it must reach the operator."""
    payload = spec() | {"target_host": "8.8.8.8"}
    response = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": payload},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "out_of_scope"
    assert "8.8.8.8" in body["detail"]
    assert "10.4.0.0/16" in body["detail"], "must say what IS allowed"


def test_malformed_spec_returns_invalid_spec(client, engagement):
    response = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": {"nonsense": 1}},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_spec"


def test_stop_and_start(client, engagement):
    tunnel_id = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    ).json()["id"]

    stopped = client.post(reverse("v1:tunnel-stop", args=[tunnel_id]))
    assert stopped.status_code == 200
    assert stopped.json()["desired_state"] == DesiredState.DOWN

    started = client.post(reverse("v1:tunnel-start", args=[tunnel_id]))
    assert started.json()["desired_state"] == DesiredState.UP


def test_delete_requests_a_stop_and_keeps_the_record(client, engagement):
    """A tunnel that existed is part of the engagement record."""
    tunnel_id = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    ).json()["id"]

    assert client.delete(reverse("v1:tunnel-detail", args=[tunnel_id])).status_code == 200
    tunnel = Tunnel.objects.get(pk=tunnel_id)
    assert tunnel.desired_state == DesiredState.DOWN


def test_routes_and_listeners(client, engagement):
    tunnel_id = client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    ).json()["id"]

    route = client.post(reverse("v1:tunnel-add-route", args=[tunnel_id]), {"cidr": "10.4.9.0/24"})
    assert route.status_code == 201
    assert route.json()["cidr"] == "10.4.9.0/24"

    denied = client.post(reverse("v1:tunnel-add-route", args=[tunnel_id]), {"cidr": "10.0.0.0/8"})
    assert denied.status_code == 400
    assert denied.json()["code"] == "out_of_scope"

    listener = client.post(
        reverse("v1:tunnel-add-listener", args=[tunnel_id]),
        {"bind_host": "10.4.0.10", "bind_port": 9000, "to_host": "127.0.0.1", "to_port": 8000},
    )
    assert listener.status_code == 201

    detail = client.get(reverse("v1:tunnel-detail", args=[tunnel_id])).json()
    assert len(detail["routes"]) == 1
    assert len(detail["listeners"]) == 1


# ── Scans ───────────────────────────────────────────────────────────────


def test_create_scan_normalises_the_target(client, engagement):
    response = client.post(
        reverse("v1:scan-list"),
        {"engagement": engagement.pk, "target": "10.4.9.7/24", "profile": "quick"},
    )
    assert response.status_code == 201
    assert response.json()["target"] == "10.4.9.0/24", "stored value must be the parsed network"


@pytest.mark.parametrize(
    "target", ["-oN /etc/cron.d/pwn", "--script=/tmp/x.nse", "10.4.0.1; id", "8.8.8.8"]
)
def test_hostile_scan_targets_are_refused(client, engagement, target):
    response = client.post(
        reverse("v1:scan-list"),
        {"engagement": engagement.pk, "target": target, "profile": "quick"},
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"invalid_target", "out_of_scope"}


def test_scope_denial_is_audited_and_visible_in_the_audit_endpoint(client, engagement):
    client.post(
        reverse("v1:scan-list"),
        {"engagement": engagement.pk, "target": "8.8.8.8", "profile": "quick"},
    )
    results = client.get(reverse("v1:audit-list"), {"result": "denied"}).json()["results"]
    assert any(e["action"] == AuditAction.SCOPE_DENIED for e in results)


# ── Engagements ─────────────────────────────────────────────────────────


def test_scope_change_is_audited_distinctly(client, engagement):
    """Widening what an engagement may touch is the most consequential edit."""
    client.patch(
        reverse("v1:engagement-detail", args=[engagement.pk]),
        {"authorized_cidrs": ["10.4.0.0/16", "10.5.0.0/16"]},
    )
    event = AuditEvent.objects.filter(action=AuditAction.ENGAGEMENT_SCOPE_CHANGED).first()
    assert event is not None
    assert "10.5.0.0/16" in str(event.payload["after"])


def test_malformed_cidr_is_rejected(client, engagement):
    """One bad entry rejects the whole edit — a half-applied scope is worse."""
    before = list(engagement.authorized_cidrs)
    response = client.patch(
        reverse("v1:engagement-detail", args=[engagement.pk]),
        {"authorized_cidrs": ["10.4.0.0/16", "garbage"]},
    )
    assert response.status_code == 400
    engagement.refresh_from_db()
    assert engagement.authorized_cidrs == before


def test_cidrs_are_normalised_on_save(client, engagement):
    """Host bits are dropped so the stored scope is exactly what gets enforced."""
    response = client.patch(
        reverse("v1:engagement-detail", args=[engagement.pk]),
        {"authorized_cidrs": ["10.4.7.9/16"]},
    )
    assert response.status_code == 200
    assert response.json()["authorized_cidrs"] == ["10.4.0.0/16"]


def test_engagement_counts_are_exposed(client, engagement):
    client.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    )
    body = client.get(reverse("v1:engagement-detail", args=[engagement.pk])).json()
    assert body["tunnel_count"] == 1


# ── Roles ───────────────────────────────────────────────────────────────


def test_viewer_can_read_but_not_write(engagement, django_user_model):
    viewer = django_user_model.objects.create_user(
        username="viewer", password="x" * 16, role=Role.VIEWER
    )
    EngagementMembership.objects.create(engagement=engagement, operator=viewer)
    api = APIClient()
    api.force_authenticate(user=viewer)

    assert api.get(reverse("v1:tunnel-list")).status_code == 200
    response = api.post(
        reverse("v1:tunnel-list"),
        {"engagement": engagement.pk, "kind": TunnelKind.SSH_LOCAL, "spec": spec()},
    )
    assert response.status_code == 403


# ── Health ──────────────────────────────────────────────────────────────


def test_health_is_public_and_says_nothing_else():
    response = APIClient().get(reverse("v1:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
