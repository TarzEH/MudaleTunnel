"""The single entry point for writing audit events."""

from __future__ import annotations

import logging
from typing import Any

from apps.audit.context import AuditContext, get_context
from apps.audit.models import AuditAction, AuditEvent, AuditResult

logger = logging.getLogger(__name__)

# Keys whose values are replaced with a placeholder before being persisted.
# Audit payloads are operational metadata, never a credential store.
REDACTED_KEYS = frozenset(
    {
        "password",
        "passphrase",
        "secret",
        "token",
        "api_key",
        "apikey",
        "key",
        "private_key",
        "credential",
        "authorization",
    }
)
REDACTED_PLACEHOLDER = "__REDACTED__"
MAX_PAYLOAD_DEPTH = 6


def record(
    action: str,
    *,
    result: str = AuditResult.OK,
    engagement=None,
    obj: Any = None,
    object_type: str = "",
    object_id: str = "",
    object_label: str = "",
    message: str = "",
    payload: dict | None = None,
    context: AuditContext | None = None,
) -> AuditEvent | None:
    """Write one audit event.

    Never raises: an audit write failing must not take down the operation it was
    describing. Failures are logged at ERROR so they surface in monitoring.
    """
    ctx = context or get_context()

    if obj is not None:
        object_type = object_type or obj.__class__.__name__.lower()
        object_id = object_id or str(getattr(obj, "pk", "") or "")
        object_label = object_label or str(obj)[:256]

    try:
        return AuditEvent.objects.create(
            actor=ctx.actor,
            actor_label=(ctx.actor_label or "system")[:128],
            action=action,
            result=result,
            engagement=engagement,
            object_type=object_type[:64],
            object_id=object_id[:64],
            object_label=object_label[:256],
            message=message,
            payload=redact(payload or {}),
            request_id=ctx.request_id or "",
            source_ip=ctx.source_ip,
        )
    except Exception:
        logger.exception("Failed to write audit event action=%s", action)
        return None


def record_denial(
    action: str,
    reason: str,
    *,
    engagement=None,
    payload: dict | None = None,
    context: AuditContext | None = None,
) -> AuditEvent | None:
    """Convenience wrapper for a policy denial.

    Denials are the entries that matter most in a post-incident review — they
    show an operator tried to reach something outside scope.
    """
    return record(
        action,
        result=AuditResult.DENIED,
        engagement=engagement,
        message=reason,
        payload=payload,
        context=context,
    )


def redact(value: Any, _depth: int = 0) -> Any:
    """Recursively strip credential-shaped values out of an audit payload."""
    if _depth > MAX_PAYLOAD_DEPTH:
        return "__TRUNCATED__"
    if isinstance(value, dict):
        return {
            k: (
                REDACTED_PLACEHOLDER
                if _is_sensitive_key(k)
                else redact(v, _depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item, _depth + 1) for item in value]
    return value


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(marker in lowered for marker in REDACTED_KEYS)


__all__ = ["AuditAction", "AuditResult", "record", "record_denial", "redact"]
