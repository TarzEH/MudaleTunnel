"""API-key issuance and authentication.

v2 had no authentication of any kind on a dashboard that runs nmap and opens
SSH tunnels. These tests pin down that the replacement actually holds.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.authentication import ApiKeyAuthentication
from apps.accounts.models import API_KEY_PREFIX, ApiKey, Role, hash_api_key

pytestmark = pytest.mark.django_db


@pytest.fixture
def issued(operator):
    return ApiKey.issue(operator=operator, name="engine daemon")


# ── Issuance ────────────────────────────────────────────────────────────


def test_plaintext_key_is_never_stored(issued):
    key, raw = issued
    key.refresh_from_db()
    assert raw.startswith(API_KEY_PREFIX)
    assert key.key_hash == hash_api_key(raw)
    assert raw not in key.key_hash
    # The hint is enough to identify the key in a list, and useless as a credential.
    assert key.key_hint == raw[: len(API_KEY_PREFIX) + 4]
    assert len(key.key_hint) < len(raw)


def test_each_key_is_unique(operator):
    _, first = ApiKey.issue(operator=operator, name="a")
    _, second = ApiKey.issue(operator=operator, name="b")
    assert first != second


# ── Authentication ──────────────────────────────────────────────────────


def authenticate(header: str | None):
    factory = APIRequestFactory()
    headers = {"HTTP_AUTHORIZATION": header} if header is not None else {}
    request = factory.get("/api/v1/engine/status/", **headers)
    return ApiKeyAuthentication().authenticate(request)


def test_valid_key_authenticates(issued, operator):
    _, raw = issued
    user, key = authenticate(f"Bearer {raw}")
    assert user == operator
    assert isinstance(key, ApiKey)


def test_unknown_key_is_rejected():
    with pytest.raises(AuthenticationFailed, match="Invalid API key"):
        authenticate(f"Bearer {API_KEY_PREFIX}not-a-real-key")


def test_revoked_key_is_rejected(issued):
    key, raw = issued
    key.revoke()
    with pytest.raises(AuthenticationFailed, match="Invalid API key"):
        authenticate(f"Bearer {raw}")


def test_revoked_and_unknown_keys_are_indistinguishable(issued):
    """The error must not tell a caller whether a key ever existed."""
    key, raw = issued
    key.revoke()

    with pytest.raises(AuthenticationFailed) as revoked:
        authenticate(f"Bearer {raw}")
    with pytest.raises(AuthenticationFailed) as unknown:
        authenticate(f"Bearer {API_KEY_PREFIX}never-existed")

    assert str(revoked.value) == str(unknown.value)


def test_disabled_operator_cannot_authenticate(issued, operator):
    _, raw = issued
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    with pytest.raises(AuthenticationFailed, match="disabled"):
        authenticate(f"Bearer {raw}")


def test_last_used_is_recorded(issued):
    key, raw = issued
    assert key.last_used_at is None
    authenticate(f"Bearer {raw}")
    key.refresh_from_db()
    assert key.last_used_at is not None


@pytest.mark.parametrize("header", [None, "", "Basic abc123", "Bearer", "Token abc123"])
def test_non_bearer_headers_fall_through(header, issued):
    """Returning None lets the next authenticator (session auth) try."""
    assert authenticate(header) is None


def test_revoke_is_idempotent(issued):
    key, _ = issued
    key.revoke()
    first = key.revoked_at
    key.revoke()
    key.refresh_from_db()
    assert key.revoked_at == first


# ── Endpoint protection ─────────────────────────────────────────────────


def test_api_requires_authentication_by_default():
    """The v2 regression: an unauthenticated caller must get nothing."""
    response = APIClient().get(reverse("v1:engine-status"))
    assert response.status_code in (401, 403)


def test_health_is_deliberately_public():
    response = APIClient().get(reverse("v1:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_authenticated_request_succeeds(issued):
    _, raw = issued
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    response = client.get(reverse("v1:engine-status"))
    assert response.status_code == 200
    assert response.json()["attached"] is False


# ── Roles ───────────────────────────────────────────────────────────────


def test_viewers_are_read_only(django_user_model):
    viewer = django_user_model.objects.create_user(
        username="viewer", password="x" * 16, role=Role.VIEWER
    )
    assert viewer.can_mutate is False
    assert viewer.is_admin is False


def test_operators_and_admins_can_mutate(django_user_model):
    operator = django_user_model.objects.create_user(
        username="op", password="x" * 16, role=Role.OPERATOR
    )
    admin = django_user_model.objects.create_user(
        username="adm", password="x" * 16, role=Role.ADMIN
    )
    assert operator.can_mutate is True
    assert admin.can_mutate is True
    assert admin.is_admin is True


def test_superuser_is_admin_regardless_of_role(django_user_model):
    root = django_user_model.objects.create_superuser(
        username="root", password="x" * 16, role=Role.VIEWER
    )
    assert root.is_admin is True
