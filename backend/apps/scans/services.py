"""Scan operations.

Same contract as ``apps.tunnels.services``: the scope check and the audit write
happen here, so no entry point can request a scan that skips them — and, for the
same reason described there, denials are recorded outside the transaction so a
rollback cannot erase them.

This is also why ``ATOMIC_REQUESTS`` is deliberately left off: a request-wide
transaction would re-introduce exactly that problem by wrapping these functions
from the outside.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record, record_denial
from apps.engagements.models import Engagement
from apps.engagements.scope import ScopeViolation
from apps.scans.models import Scan, ScanProfile, ScanStatus, Service
from apps.scans.parsers import ParsedScan

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """The operator's role does not allow this action."""


def request_scan(
    *,
    engagement: Engagement,
    target: str,
    profile: str = ScanProfile.STANDARD,
    operator=None,
    via_tunnel=None,
) -> Scan:
    """Queue a scan after validating the target.

    The stored ``target`` is the *normalised* form produced by the scope check,
    not the operator's raw input — so what the engine later runs is a value that
    provably parsed as a network.
    """
    if operator is not None:
        if not operator.can_mutate:
            raise PermissionDenied("Your role is read-only")
        from apps.engagements.models import EngagementMembership
        membership = EngagementMembership.objects.filter(
            engagement=engagement, operator=operator
        ).first()
        if membership is not None and not membership.can_mutate:
            raise PermissionDenied(
                f"Your engagement role ({membership.get_role_display()}) is read-only"
            )

    if profile not in ScanProfile._value2member_map_:
        raise ValueError(f"Unknown scan profile {profile!r}")

    try:
        network = engagement.check_network(target)
    except ScopeViolation as exc:
        record_denial(
            AuditAction.SCOPE_DENIED,
            str(exc),
            engagement=engagement,
            payload={"target": target, "profile": profile},
        )
        raise

    with transaction.atomic():
        scan = Scan.objects.create(
            engagement=engagement,
            target=str(network),
            profile=profile,
            via_tunnel=via_tunnel,
            status=ScanStatus.QUEUED,
            requested_by=operator,
        )
        record(
            AuditAction.SCAN_REQUESTED,
            engagement=engagement,
            obj=scan,
            message=f"{profile} scan of {network}",
            payload={"target": str(network), "profile": profile},
        )
    return scan


@transaction.atomic
def ingest_results(scan: Scan, parsed: ParsedScan, *, raw_xml: str = "") -> int:
    """Persist parsed scan output. Called by the engine daemon only.

    Idempotent: re-ingesting the same scan replaces its services rather than
    duplicating them, so a retried or resumed ingest cannot inflate counts.
    """
    Service.objects.filter(scan=scan).delete()

    services = [
        Service(
            scan=scan,
            engagement=scan.engagement,
            host=item.host,
            hostname=item.hostname,
            port=item.port,
            protocol=item.protocol,
            state=_normalise_state(item.state),
            service_name=item.service_name,
            product=item.product,
            version=item.version,
            extra_info=item.extra_info,
        )
        for item in parsed.services
    ]
    Service.objects.bulk_create(services, ignore_conflicts=True)

    scan.raw_stdout = raw_xml
    scan.hosts_up = parsed.hosts_up
    scan.services_found = len(services)
    scan.status = ScanStatus.COMPLETED
    scan.finished_at = timezone.now()
    scan.save(
        update_fields=[
            "raw_stdout", "hosts_up", "services_found", "status", "finished_at",
        ]
    )

    # A scan run through a pivot is evidence of what that pivot can reach.
    from apps.tunnels.pivot import refresh_agent_reachability

    refresh_agent_reachability(scan)

    record(
        AuditAction.SCAN_COMPLETED,
        engagement=scan.engagement,
        obj=scan,
        message=f"{len(services)} services on {parsed.hosts_up} hosts",
        payload={"services": len(services), "hosts_up": parsed.hosts_up},
    )
    return len(services)


@transaction.atomic
def mark_failed(scan: Scan, error: str, *, status: str = ScanStatus.FAILED) -> Scan:
    scan.status = status
    scan.error = error[:4000]
    scan.finished_at = timezone.now()
    scan.save(update_fields=["status", "error", "finished_at"])
    record(
        AuditAction.SCAN_FAILED,
        result="error",
        engagement=scan.engagement,
        obj=scan,
        message=error[:500],
    )
    return scan


def _normalise_state(state: str) -> str:
    """Map nmap's state strings onto the model's choices."""
    normalised = (state or "").strip().lower()
    if normalised in Service.State.values:
        return normalised
    # nmap also emits states like "unfiltered"; record the closest usable value
    # rather than dropping a genuine finding.
    return Service.State.OPEN if "open" in normalised else Service.State.FILTERED
