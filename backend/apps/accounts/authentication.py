"""API-key authentication for DRF.

Header form:  ``Authorization: Bearer mdlt_<token>``
"""

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.accounts.models import ApiKey, hash_api_key

_SCHEME = "bearer"


class ApiKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != _SCHEME:
            return None

        raw_key = parts[1]
        try:
            key = ApiKey.objects.active().select_related("operator").get(
                key_hash=hash_api_key(raw_key)
            )
        except ApiKey.DoesNotExist:
            # Same message for unknown and revoked keys — don't leak which.
            raise exceptions.AuthenticationFailed("Invalid API key") from None

        if not key.operator.is_active:
            raise exceptions.AuthenticationFailed("Operator account is disabled")

        # Cheap enough at our request volume, and worth having in the audit trail.
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())

        return (key.operator, key)

    def authenticate_header(self, request) -> str:
        return self.keyword
