"""Tunnel operations.

Every caller — REST API, CLI, admin action — goes through these functions
rather than touching the models directly. That is what makes the policy
enforceable: scope checks, role checks, spec validation and audit writes happen
in one place, so a new entry point cannot accidentally skip them.

Nothing here starts a process. These functions record *desired* state; the
engine daemon observes it and reconciles.

**Transaction shape matters here.** Validation and denial-auditing run *outside*
the transaction, and only the successful write is wrapped in one. Wrapping the
whole function instead would roll the denial record back along with the refused
operation, so every blocked attempt would vanish from the audit trail — which is
precisely the entry an incident review needs.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.audit.models import AuditAction
from apps.audit.services import record, record_denial
from apps.engagements.models import Engagement
from apps.engagements.scope import ScopeViolation
from apps.tunnels.models import DesiredState, Tunnel, TunnelKind, TunnelStatus
from mudale_engine.specs import SpecError, parse_spec

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """The operator's role does not allow this action."""


#: Which spec fields name a host that has to be inside the engagement's scope.
#:
#: Only the *far side* of a tunnel is scope-checked. ``local_bind`` is an
#: address on the operator's own machine and is deliberately not checked against
#: the client's ranges — binding 127.0.0.1 locally is not "touching" the client.
SCOPED_HOST_FIELDS: dict[str, tuple[str, ...]] = {
    TunnelKind.SSH_LOCAL: ("endpoint.host", "target_host"),
    TunnelKind.SSH_DYNAMIC: ("endpoint.host",),
    TunnelKind.SSH_REMOTE: ("endpoint.host",),
    TunnelKind.SSH_REMOTE_DYNAMIC: ("endpoint.host",),
}


def _require_mutation(operator, engagement: Engagement | None = None) -> None:
    if operator is None:
        return
    if not operator.can_mutate:
        raise PermissionDenied("Your role is read-only")
    if engagement is not None:
        from apps.engagements.models import EngagementMembership
        membership = EngagementMembership.objects.filter(
            engagement=engagement, operator=operator
        ).first()
        if membership is not None and not membership.can_mutate:
            raise PermissionDenied(
                f"Your engagement role ({membership.get_role_display()}) is read-only"
            )


def _resolve(spec, dotted: str):
    value = spec
    for part in dotted.split("."):
        value = getattr(value, part)
    return value


def check_spec_scope(engagement: Engagement, kind: str, spec) -> None:
    """Validate every scoped host in a spec against the engagement.

    ``target_host`` of a *remote* forward is intentionally exempt: on a reverse
    forward the target is reached from the operator's own machine (usually
    127.0.0.1), not from inside the client network.
    """
    for field in SCOPED_HOST_FIELDS.get(kind, ()):
        value = _resolve(spec, field)
        if value:
            engagement.check_host(str(value))


def create_tunnel(
    *,
    engagement: Engagement,
    kind: str,
    spec: dict,
    operator=None,
    agent=None,
    label: str = "",
) -> Tunnel:
    """Record a request for a new tunnel.

    Raises :class:`SpecError` for a malformed spec, :class:`ScopeViolation` for
    an out-of-scope or non-operational engagement, and :class:`PermissionDenied`
    for a read-only role. Denials are audited before the exception propagates —
    a blocked attempt is exactly what a post-incident review needs to see.
    """
    _require_mutation(operator, engagement)

    try:
        parsed = parse_spec(kind, spec)
    except SpecError as exc:
        record_denial(
            AuditAction.TUNNEL_REQUESTED,
            str(exc),
            engagement=engagement,
            payload={"kind": kind, "spec": spec},
        )
        raise

    try:
        check_spec_scope(engagement, kind, parsed)
    except ScopeViolation as exc:
        record_denial(
            AuditAction.SCOPE_DENIED,
            str(exc),
            engagement=engagement,
            payload={"kind": kind, "spec": spec},
        )
        raise

    with transaction.atomic():
        tunnel = Tunnel.objects.create(
            engagement=engagement,
            agent=agent,
            kind=kind,
            label=label,
            spec=parsed.model_dump(mode="json"),
            desired_state=DesiredState.UP,
            status=TunnelStatus.PENDING,
            created_by=operator,
        )
        record(
            AuditAction.TUNNEL_REQUESTED,
            engagement=engagement,
            obj=tunnel,
            message=f"Requested {tunnel.get_kind_display()}",
            payload={"kind": kind, "spec": tunnel.spec},
        )
    return tunnel


@transaction.atomic
def request_stop(tunnel: Tunnel, *, operator=None) -> Tunnel:
    """Ask the engine to bring a tunnel down.

    Returns immediately: the daemon owns the process and performs the actual
    stop. The status only becomes STOPPED once the daemon has confirmed it.
    """
    _require_mutation(operator, tunnel.engagement)

    tunnel.desired_state = DesiredState.DOWN
    tunnel.save(update_fields=["desired_state", "updated_at"])

    record(
        AuditAction.TUNNEL_STOPPED,
        engagement=tunnel.engagement,
        obj=tunnel,
        message="Stop requested",
    )
    return tunnel


def request_start(tunnel: Tunnel, *, operator=None) -> Tunnel:
    """Bring a stopped tunnel back up, reusing its existing spec."""
    _require_mutation(operator, tunnel.engagement)

    # Re-check scope: the engagement may have been narrowed, paused or expired
    # since the tunnel was first created.
    parsed = parse_spec(tunnel.kind, tunnel.spec)
    try:
        check_spec_scope(tunnel.engagement, tunnel.kind, parsed)
    except ScopeViolation as exc:
        record_denial(
            AuditAction.SCOPE_DENIED, str(exc), engagement=tunnel.engagement,
            payload={"tunnel_id": tunnel.pk},
        )
        raise

    with transaction.atomic():
        tunnel.desired_state = DesiredState.UP
        tunnel.status = TunnelStatus.PENDING
        tunnel.last_error = ""
        tunnel.save(update_fields=["desired_state", "status", "last_error", "updated_at"])
        record(
            AuditAction.TUNNEL_REQUESTED,
            engagement=tunnel.engagement,
            obj=tunnel,
            message="Restart requested",
        )
    return tunnel


