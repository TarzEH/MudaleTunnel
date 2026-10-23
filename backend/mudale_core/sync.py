"""CLI ↔ Dashboard sync bridge.

Reads tunnel/scan/service state from the standalone SQLite database and
pushes it into the Django PostgreSQL models, so work done in the CLI is
visible in the web dashboard (and vice-versa).

The bridge is **unidirectional per entity per direction**:

    CLI (SQLite)  ──push──>  Dashboard (PostgreSQL)
        tunnels, scans, services created in the CLI

    Dashboard (PostgreSQL)  ──pull──>  CLI (SQLite)
        tunnels with desired_state changes from the dashboard

Sync tracking lives in a ``sync_state`` table inside the SQLite database.
Each row records the SQLite id, the Django pk, the entity type, and the
last-synced timestamp so we never duplicate.

Usage (inside the console or daemon when Django is available)::

    from mudale_core.sync import SyncBridge
    bridge = SyncBridge(state_db, engagement_id=1)
    report = bridge.push_all()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mudale_core.state import StateDB

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_state (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    local_id    INTEGER NOT NULL,
    remote_id   INTEGER NOT NULL,
    synced_at   REAL NOT NULL,
    UNIQUE(entity_type, local_id)
);
"""


@dataclass
class SyncReport:
    tunnels_pushed: int = 0
    tunnels_updated: int = 0
    scans_pushed: int = 0
    scans_updated: int = 0
    services_pushed: int = 0
    tunnels_pulled: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total(self) -> int:
        return (
            self.tunnels_pushed + self.tunnels_updated
            + self.scans_pushed + self.scans_updated
            + self.services_pushed + self.tunnels_pulled
        )


def _epoch_to_datetime(epoch: float | None) -> datetime | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC)


class SyncBridge:
    """Bidirectional sync between mudale_core SQLite and Django PostgreSQL."""

    def __init__(
        self,
        db: StateDB,
        engagement_id: int,
        workspace_id: int | None = None,
    ):
        self.db = db
        self.engagement_id = engagement_id
        self.workspace_id = workspace_id
        self._ensure_sync_table()

    def _ensure_sync_table(self) -> None:
        with self.db._conn() as conn:
            conn.executescript(SYNC_SCHEMA)

    def _get_remote_id(self, entity_type: str, local_id: int) -> int | None:
        with self.db._conn() as conn:
            row = conn.execute(
                "SELECT remote_id FROM sync_state "
                "WHERE entity_type = ? AND local_id = ?",
                (entity_type, local_id),
            ).fetchone()
            return row["remote_id"] if row else None

    def _set_remote_id(self, entity_type: str, local_id: int, remote_id: int) -> None:
        with self.db._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state "
                "(entity_type, local_id, remote_id, synced_at) VALUES (?, ?, ?, ?)",
                (entity_type, local_id, remote_id, time.time()),
            )

    def _get_local_id(self, entity_type: str, remote_id: int) -> int | None:
        with self.db._conn() as conn:
            row = conn.execute(
                "SELECT local_id FROM sync_state "
                "WHERE entity_type = ? AND remote_id = ?",
                (entity_type, remote_id),
            ).fetchone()
            return row["local_id"] if row else None

    def _import_django_models(self):
        from apps.scans.models import Scan, Service
        from apps.tunnels.models import Tunnel

        return Tunnel, Scan, Service

    # ── Push: CLI → Dashboard ─────────────────────────────────────────

    def push_all(self) -> SyncReport:
        report = SyncReport()
        self._push_tunnels(report)
        self._push_scans(report)
        self._push_services(report)
        return report

    def _push_tunnels(self, report: SyncReport) -> None:
        from django.db import transaction

        from apps.audit.models import AuditAction
        from apps.audit.services import record, record_denial
        from apps.engagements.models import Engagement
        from apps.engagements.scope import ScopeViolation
        from apps.tunnels.services import check_spec_scope
        from mudale_engine.specs import SpecError, parse_spec

        Tunnel, _, _ = self._import_django_models()
        engagement = Engagement.objects.get(pk=self.engagement_id)

        ws_id = self.workspace_id
        tunnels = self.db.list_tunnels(workspace_id=ws_id)

        for rec in tunnels:
            remote_id = self._get_remote_id("tunnel", rec.id)

            if remote_id is not None:
                try:
                    obj = Tunnel.objects.get(pk=remote_id)
                    obj.status = rec.status
                    obj.pid = rec.pid
                    obj.last_error = rec.last_error
                    obj.restart_count = rec.restart_count
                    obj.started_at = _epoch_to_datetime(rec.started_at)
                    obj.stopped_at = _epoch_to_datetime(rec.stopped_at)
                    obj.save(update_fields=[
                        "status", "pid", "last_error",
                        "restart_count", "started_at", "stopped_at", "updated_at",
                    ])
                    report.tunnels_updated += 1
                except Tunnel.DoesNotExist:
                    report.errors.append(f"Tunnel remote_id={remote_id} vanished from dashboard")
                continue

            try:
                parsed = parse_spec(rec.kind, rec.spec)
            except SpecError as exc:
                record_denial(
                    AuditAction.TUNNEL_REQUESTED,
                    str(exc),
                    engagement=engagement,
                    payload={"kind": rec.kind, "spec": rec.spec, "source": "cli-sync"},
                )
                report.errors.append(f"Tunnel {rec.id} spec invalid: {exc}")
                continue

            try:
                check_spec_scope(engagement, rec.kind, parsed)
            except ScopeViolation as exc:
                record_denial(
                    AuditAction.SCOPE_DENIED,
                    str(exc),
                    engagement=engagement,
                    payload={"kind": rec.kind, "spec": rec.spec, "source": "cli-sync"},
                )
                report.errors.append(f"Tunnel {rec.id} out of scope: {exc}")
                continue

            with transaction.atomic():
                obj = Tunnel.objects.create(
                    engagement_id=self.engagement_id,
                    kind=rec.kind,
                    label=rec.label or f"cli-tunnel-{rec.id}",
                    desired_state=rec.desired_state,
                    spec=parsed.model_dump(mode="json"),
                    status=rec.status,
                    pid=rec.pid,
                    last_error=rec.last_error,
                    restart_count=rec.restart_count,
                    started_at=_epoch_to_datetime(rec.started_at),
                    stopped_at=_epoch_to_datetime(rec.stopped_at),
                    owner_engine_id="cli-standalone",
                )
                record(
                    AuditAction.TUNNEL_REQUESTED,
                    engagement=engagement,
                    obj=obj,
                    message=f"Synced from CLI: {obj.get_kind_display()}",
                    payload={"kind": rec.kind, "spec": obj.spec, "source": "cli-sync"},
                )
            self._set_remote_id("tunnel", rec.id, obj.pk)
            report.tunnels_pushed += 1

    def _push_scans(self, report: SyncReport) -> None:
        from django.db import transaction

        from apps.audit.models import AuditAction
        from apps.audit.services import record, record_denial
        from apps.engagements.models import Engagement
        from apps.engagements.scope import ScopeViolation
        from apps.scans.models import ScanProfile

        _, Scan, _ = self._import_django_models()
        engagement = Engagement.objects.get(pk=self.engagement_id)

        ws_id = self.workspace_id
        scans = self.db.list_scans(workspace_id=ws_id)

        for rec in scans:
            remote_id = self._get_remote_id("scan", rec.id)

            if remote_id is not None:
                try:
                    obj = Scan.objects.get(pk=remote_id)
                    obj.status = rec.status
                    obj.hosts_up = rec.hosts_up
                    obj.services_found = rec.services_found
                    obj.error = rec.error
                    obj.started_at = _epoch_to_datetime(rec.started_at)
                    obj.finished_at = _epoch_to_datetime(rec.finished_at)
                    obj.save(update_fields=[
                        "status", "hosts_up", "services_found", "error",
                        "started_at", "finished_at",
                    ])
                    report.scans_updated += 1
                except Scan.DoesNotExist:
                    report.errors.append(f"Scan remote_id={remote_id} vanished from dashboard")
                continue

            if rec.profile not in ScanProfile._value2member_map_:
                report.errors.append(f"Scan {rec.id} unknown profile {rec.profile!r}")
                continue

            try:
                network = engagement.check_network(rec.target)
            except ScopeViolation as exc:
                record_denial(
                    AuditAction.SCOPE_DENIED,
                    str(exc),
                    engagement=engagement,
                    payload={"target": rec.target, "profile": rec.profile, "source": "cli-sync"},
                )
                report.errors.append(f"Scan {rec.id} target out of scope: {exc}")
                continue

            tunnel_remote_id = None
            if rec.via_tunnel_id:
                tunnel_remote_id = self._get_remote_id("tunnel", rec.via_tunnel_id)

            with transaction.atomic():
                obj = Scan.objects.create(
                    engagement_id=self.engagement_id,
                    target=str(network),
                    profile=rec.profile,
                    via_tunnel_id=tunnel_remote_id,
                    status=rec.status,
                    hosts_up=rec.hosts_up,
                    services_found=rec.services_found,
                    error=rec.error,
                    raw_stdout=rec.xml_output,
                    started_at=_epoch_to_datetime(rec.started_at),
                    finished_at=_epoch_to_datetime(rec.finished_at),
                    owner_engine_id="cli-standalone",
                )
                record(
                    AuditAction.SCAN_REQUESTED,
                    engagement=engagement,
                    obj=obj,
                    message=f"Synced from CLI: {rec.profile} scan of {network}",
                    payload={"target": str(network), "profile": rec.profile, "source": "cli-sync"},
                )
            self._set_remote_id("scan", rec.id, obj.pk)
            report.scans_pushed += 1

    def _push_services(self, report: SyncReport) -> None:
        _, _, Service = self._import_django_models()

        ws_id = self.workspace_id
        services = self.db.list_services(workspace_id=ws_id)

        for rec in services:
            remote_id = self._get_remote_id("service", rec.id)
            if remote_id is not None:
                continue

            scan_remote_id = self._get_remote_id("scan", rec.scan_id)
            if scan_remote_id is None:
                report.errors.append(
                    f"Service {rec.id} references scan {rec.scan_id} "
                    "which hasn't been synced yet"
                )
                continue

            obj = Service.objects.create(
                scan_id=scan_remote_id,
                engagement_id=self.engagement_id,
                host=rec.host,
                hostname=rec.hostname,
                port=rec.port,
                protocol=rec.protocol,
                state=rec.state,
                service_name=rec.service_name,
                product=rec.product,
                version=rec.version,
                extra_info=rec.extra_info,
            )
            self._set_remote_id("service", rec.id, obj.pk)
            report.services_pushed += 1

    # ── Pull: Dashboard → CLI ─────────────────────────────────────────

    def pull_tunnel_commands(self) -> SyncReport:
        """Pull desired_state changes from the dashboard into CLI state."""
        Tunnel, _, _ = self._import_django_models()
        report = SyncReport()

        dashboard_tunnels = Tunnel.objects.filter(
            engagement_id=self.engagement_id,
            owner_engine_id="cli-standalone",
        )

        for obj in dashboard_tunnels:
            local_id = self._get_local_id("tunnel", obj.pk)
            if local_id is None:
                continue

            local_rec = self.db.get_tunnel(local_id)
            if local_rec is None:
                continue

            if obj.desired_state != local_rec.desired_state:
                self.db.update_tunnel(local_id, desired_state=obj.desired_state)
                report.tunnels_pulled += 1

        return report

    # ── Full sync (both directions) ───────────────────────────────────

    def sync(self) -> SyncReport:
        push_report = self.push_all()
        pull_report = self.pull_tunnel_commands()
        push_report.tunnels_pulled = pull_report.tunnels_pulled
        push_report.errors.extend(pull_report.errors)
        return push_report
