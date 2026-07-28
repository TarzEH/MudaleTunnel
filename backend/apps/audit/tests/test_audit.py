"""Audit trail behaviour — append-only guarantees and redaction."""

from __future__ import annotations

import pytest

from apps.audit.context import AuditContext, using
from apps.audit.models import AppendOnlyError, AuditAction, AuditEvent, AuditResult
from apps.audit.services import record, record_denial, redact

pytestmark = pytest.mark.django_db


# ── Append-only ─────────────────────────────────────────────────────────


def test_event_cannot_be_modified(engagement):
    event = record(AuditAction.TUNNEL_STARTED, engagement=engagement, message="original")
    event.message = "tampered"
    with pytest.raises(AppendOnlyError, match="cannot be modified"):
        event.save()


def test_event_cannot_be_deleted(engagement):
    event = record(AuditAction.TUNNEL_STARTED, engagement=engagement)
    with pytest.raises(AppendOnlyError, match="cannot be deleted"):
        event.delete()


def test_event_survives_actor_deletion(engagement, operator):
    """The audit trail has to outlive the account that produced it."""
    with using(AuditContext(actor=operator, actor_label="opsec")):
        event = record(AuditAction.TUNNEL_STARTED, engagement=engagement)

    operator.delete()
    event.refresh_from_db()

    assert event.actor is None
    assert event.actor_label == "opsec"


def test_event_survives_object_deletion(engagement):
    """object_type/object_id are a loose reference, not a FK, for this reason."""
    event = record(
        AuditAction.ENGAGEMENT_CREATED, engagement=engagement, obj=engagement
    )
    object_label = event.object_label
    engagement.delete()

    event.refresh_from_db()
    assert event.engagement is None
    assert event.object_label == object_label


# ── Context propagation ─────────────────────────────────────────────────


def test_actor_and_request_context_are_recorded(engagement, operator):
    context = AuditContext(
        actor=operator,
        actor_label="opsec",
        request_id="0d1a5b0e-0000-4000-8000-000000000000",
        source_ip="10.0.0.5",
    )
    with using(context):
        event = record(AuditAction.SCAN_REQUESTED, engagement=engagement)

    assert event.actor == operator
    assert event.request_id == "0d1a5b0e-0000-4000-8000-000000000000"
    assert event.source_ip == "10.0.0.5"


def test_engine_actions_are_attributed_to_system(engagement):
    event = record(AuditAction.AGENT_DISCONNECTED, engagement=engagement)
    assert event.actor is None
    assert event.actor_label == "system"


def test_object_reference_is_derived_from_the_instance(engagement):
    event = record(AuditAction.ENGAGEMENT_UPDATED, obj=engagement)
    assert event.object_type == "engagement"
    assert event.object_id == str(engagement.pk)
    assert event.object_label == str(engagement)


# ── Denials ─────────────────────────────────────────────────────────────


def test_denial_is_recorded_with_its_reason(engagement):
    """Denials are the entries that matter most in a post-incident review."""
    event = record_denial(
        AuditAction.SCOPE_DENIED,
        "172.16.0.0/24 is not inside any authorised range",
        engagement=engagement,
        payload={"target": "172.16.0.0/24"},
    )
    assert event.result == AuditResult.DENIED
    assert "not inside any authorised range" in event.message
    assert event.payload["target"] == "172.16.0.0/24"


# ── Redaction ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key", ["password", "ssh_password", "api_key", "TOKEN", "private_key", "Authorization"]
)
def test_credential_shaped_keys_are_redacted(key):
    assert redact({key: "hunter2"})[key] == "__REDACTED__"


def test_redaction_reaches_nested_structures():
    """Traversal continues through dicts and lists under non-sensitive keys."""
    payload = {"endpoint": {"user": "opsec", "auth": [{"password": "hunter2"}]}}
    cleaned = redact(payload)
    assert cleaned["endpoint"]["user"] == "opsec"
    assert cleaned["endpoint"]["auth"][0]["password"] == "__REDACTED__"


def test_sensitive_key_redacts_its_whole_subtree():
    """A container named for a credential is replaced entirely, not walked into.

    Conservative on purpose: anything filed under "credentials" is assumed to be
    one, whatever shape it has, so an unexpected structure cannot leak a value
    that no key name happened to match.
    """
    payload = {"credentials": [{"user": "opsec", "secret": "hunter2"}]}
    assert redact(payload)["credentials"] == "__REDACTED__"


def test_redaction_is_depth_bounded():
    """A self-referential or absurdly deep payload must not recurse forever."""
    payload: dict = {}
    node = payload
    for _ in range(50):
        node["next"] = {}
        node = node["next"]
    assert "__TRUNCATED__" in str(redact(payload))


def test_secrets_never_reach_the_database(engagement):
    event = record(
        AuditAction.TUNNEL_REQUESTED,
        engagement=engagement,
        payload={"host": "10.4.0.10", "password": "hunter2"},
    )
    event.refresh_from_db()
    assert event.payload["host"] == "10.4.0.10"
    assert event.payload["password"] == "__REDACTED__"
    assert "hunter2" not in str(event.payload)


# ── Resilience ──────────────────────────────────────────────────────────


def test_audit_failure_does_not_raise(monkeypatch, engagement):
    """An audit write failing must never take down the operation it describes."""

    def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(AuditEvent.objects, "create", explode)
    assert record(AuditAction.TUNNEL_STARTED, engagement=engagement) is None
