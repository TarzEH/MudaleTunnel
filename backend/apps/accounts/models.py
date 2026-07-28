"""Operators and machine credentials.

API keys are stored only as a SHA-256 hash. The plaintext is returned exactly
once, at creation time, and is unrecoverable afterwards.
"""

import hashlib
import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

# 32 bytes of entropy, urlsafe-encoded. The prefix makes keys greppable in logs
# and lets secret scanners recognise a leaked MudaleTunnel key.
API_KEY_PREFIX = "mdlt_"
API_KEY_BYTES = 32


def generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_BYTES)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    OPERATOR = "operator", "Operator"
    VIEWER = "viewer", "Viewer"


class Operator(AbstractUser):
    """A human using the control plane."""

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.OPERATOR)
    # Free-text handle shown in the audit log and on live sessions.
    callsign = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "operator"
        verbose_name_plural = "operators"

    def __str__(self) -> str:
        return self.callsign or self.get_username()

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def can_mutate(self) -> bool:
        """Viewers get read-only access to everything."""
        return self.is_admin or self.role == Role.OPERATOR


class ApiKeyQuerySet(models.QuerySet):
    def active(self) -> "ApiKeyQuerySet":
        return self.filter(revoked_at__isnull=True)


class ApiKey(models.Model):
    """A non-interactive credential, for CLI clients and the engine daemon."""

    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=128)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    # Stored so the UI can show "mdlt_A1b2…" without holding the secret.
    key_hint = models.CharField(max_length=16, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ApiKeyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["key_hash"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_hint}…)"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self) -> None:
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])

    @classmethod
    def issue(cls, *, operator: Operator, name: str) -> tuple["ApiKey", str]:
        """Create a key and return it alongside the one-time plaintext."""
        raw = generate_api_key()
        key = cls.objects.create(
            operator=operator,
            name=name,
            key_hash=hash_api_key(raw),
            key_hint=raw[: len(API_KEY_PREFIX) + 4],
        )
        return key, raw
