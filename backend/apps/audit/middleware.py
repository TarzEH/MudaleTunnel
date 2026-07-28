"""Populates the audit context for the lifetime of each request."""

from __future__ import annotations

import uuid

from apps.audit.context import SYSTEM_ACTOR_LABEL, AuditContext, reset_context, set_context

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"


class AuditContextMiddleware:
    """Attaches actor, request id and source IP to the ambient audit context.

    The request id is echoed back on the response so a UI error can be tied to
    an audit entry without digging through server logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = _incoming_request_id(request) or str(uuid.uuid4())
        request.audit_request_id = request_id

        token = set_context(
            AuditContext(
                # Left unset on purpose: authentication has not run yet. The
                # request is carried instead, and the actor is resolved from it
                # at write time, by which point request.user is populated.
                actor=None,
                actor_label=SYSTEM_ACTOR_LABEL,
                request_id=request_id,
                source_ip=_client_ip(request),
                request=request,
            )
        )
        try:
            response = self.get_response(request)
        finally:
            reset_context(token)

        response["X-Request-ID"] = request_id
        return response


def context_for(request) -> AuditContext:
    """Build an audit context from a request whose user has been resolved.

    Views and DRF handlers call this because ``request.user`` is not populated
    when the middleware runs.
    """
    user = getattr(request, "user", None)
    authenticated = bool(user and getattr(user, "is_authenticated", False))
    return AuditContext(
        actor=user if authenticated else None,
        actor_label=str(user) if authenticated else "anonymous",
        request_id=getattr(request, "audit_request_id", ""),
        source_ip=_client_ip(request),
    )


def _incoming_request_id(request) -> str:
    """Accept a caller-supplied request id only if it is a well-formed UUID.

    Echoing an arbitrary client string into a database column and a response
    header is a log-injection footgun; requiring a UUID removes it.
    """
    raw = request.META.get(REQUEST_ID_HEADER, "")
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError, TypeError):
        return ""


def _client_ip(request) -> str | None:
    """The peer address.

    Deliberately ignores ``X-Forwarded-For``: it is trivially spoofable unless a
    trusted proxy is known to overwrite it, and a forged source IP in an audit
    trail is worse than no source IP. Deployments behind a real proxy should set
    ``USE_X_FORWARDED_HOST``/a dedicated proxy middleware and revisit this.
    """
    return request.META.get("REMOTE_ADDR") or None
