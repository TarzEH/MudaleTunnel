"""QA test suite — CLI ↔ Dashboard session continuity.

Verifies that state created in the standalone CLI (SQLite) is accurately
reflected in the web dashboard (Django PostgreSQL) after a sync, and that
dashboard commands flow back to the CLI engine.

Test domains:
    1. State persistence — tunnels, scans, services carry over
    2. Module initialisation — spec shapes survive the round-trip
    3. Seamless transition — status updates propagate both directions
    4. Edge cases — partial sync, vanished rows, concurrent writes
"""

from __future__ import annotations

import time

import pytest

from mudale_core.state import StateDB
from mudale_core.sync import SyncBridge, _epoch_to_datetime
from mudale_engine.enums import (
    DesiredState,
    ScanStatus,
    TunnelKind,
    TunnelStatus,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sqlite_db(tmp_path):
    """Fresh SQLite state database in a temp directory."""
    db = StateDB(tmp_path / "mudale.db")
    ws = db.ensure_default_workspace()
    return db, ws


@pytest.fixture
def bridge(sqlite_db, engagement):
    """SyncBridge wired to the temp SQLite and the test engagement."""
    db, ws = sqlite_db
    return SyncBridge(db=db, engagement_id=engagement.pk, workspace_id=ws.id)


# ═══════════════════════════════════════════════════════════════════════
# 1. STATE PERSISTENCE — tunnels, scans, services carry over
# ═══════════════════════════════════════════════════════════════════════


class TestTunnelPersistence:
    """TC-SP-001 through TC-SP-005: tunnel state round-trip."""

    def test_push_new_tunnel_creates_dashboard_row(self, sqlite_db, bridge):
        """TC-SP-001: A tunnel created in CLI appears in the dashboard."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1080,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="socks-pivot")
        db.update_tunnel(rec.id, status=TunnelStatus.ACTIVE, started_at=time.time())

        report = bridge.push_all()

        assert report.tunnels_pushed == 1
        assert report.tunnels_updated == 0
        assert not report.errors

        from apps.tunnels.models import Tunnel

        dashboard_tunnel = Tunnel.objects.get(label="socks-pivot")
        assert dashboard_tunnel.kind == TunnelKind.SSH_DYNAMIC
        assert dashboard_tunnel.status == TunnelStatus.ACTIVE
        assert dashboard_tunnel.spec["local_port"] == 1080
        assert dashboard_tunnel.engagement_id == bridge.engagement_id
        assert dashboard_tunnel.owner_engine_id == "cli-standalone"

    def test_push_idempotent_no_duplicates(self, sqlite_db, bridge):
        """TC-SP-002: Pushing the same tunnel twice does not create a duplicate."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1081,
        }
        db.create_tunnel(ws.id, TunnelKind.SSH_LOCAL, spec, label="idempotent-test")

        bridge.push_all()
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        assert Tunnel.objects.filter(label="idempotent-test").count() == 1

    def test_push_updates_status_change(self, sqlite_db, bridge):
        """TC-SP-003: A status change in CLI propagates to the dashboard."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1082,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="status-test")
        db.update_tunnel(rec.id, status=TunnelStatus.ACTIVE)

        bridge.push_all()

        db.update_tunnel(rec.id, status=TunnelStatus.FAILED, last_error="Connection reset")
        report = bridge.push_all()

        assert report.tunnels_updated == 1

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="status-test")
        assert obj.status == TunnelStatus.FAILED
        assert obj.last_error == "Connection reset"

    def test_push_preserves_spec_fields(self, sqlite_db, bridge):
        """TC-SP-004: All spec fields survive the SQLite → PostgreSQL transfer."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root",
                         "identity_file": "/root/.ssh/id_rsa"},
            "local_bind": "127.0.0.1",
            "local_port": 1083,
            "target_host": "10.10.10.50",
            "target_port": 3306,
        }
        db.create_tunnel(ws.id, TunnelKind.SSH_LOCAL, spec, label="spec-test")
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="spec-test")
        assert obj.spec == spec

    def test_push_multiple_tunnels(self, sqlite_db, bridge):
        """TC-SP-005: Multiple tunnels sync in one push."""
        db, ws = sqlite_db
        for i in range(5):
            spec = {
                "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
                "local_bind": "127.0.0.1",
                "local_port": 2000 + i,
            }
            db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label=f"bulk-{i}")

        report = bridge.push_all()
        assert report.tunnels_pushed == 5

        from apps.tunnels.models import Tunnel

        assert Tunnel.objects.filter(label__startswith="bulk-").count() == 5


class TestScanPersistence:
    """TC-SP-010 through TC-SP-014: scan state round-trip."""

    def test_push_completed_scan(self, sqlite_db, bridge):
        """TC-SP-010: A completed scan with results appears in the dashboard."""
        db, ws = sqlite_db
        rec = db.create_scan(ws.id, "10.10.10.0/24", "standard")
        db.update_scan(
            rec.id, status=ScanStatus.COMPLETED,
            hosts_up=3, services_found=12,
            started_at=time.time() - 60, finished_at=time.time(),
            xml_output="<nmaprun>...</nmaprun>",
        )

        report = bridge.push_all()

        assert report.scans_pushed == 1

        from apps.scans.models import Scan

        obj = Scan.objects.get(target="10.10.10.0/24")
        assert obj.status == ScanStatus.COMPLETED
        assert obj.hosts_up == 3
        assert obj.services_found == 12
        assert obj.raw_stdout == "<nmaprun>...</nmaprun>"

    def test_push_scan_linked_to_tunnel(self, sqlite_db, bridge):
        """TC-SP-011: A scan routed via a tunnel keeps the FK relationship."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1090,
        }
        tunnel = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec)
        scan = db.create_scan(ws.id, "10.10.10.0/24", "quick", via_tunnel_id=tunnel.id)
        db.update_scan(scan.id, status=ScanStatus.COMPLETED)

        bridge.push_all()

        from apps.scans.models import Scan
        from apps.tunnels.models import Tunnel

        scan_obj = Scan.objects.get(target="10.10.10.0/24")
        tunnel_obj = Tunnel.objects.get(engagement_id=bridge.engagement_id)

        assert scan_obj.via_tunnel_id == tunnel_obj.pk

    def test_push_failed_scan(self, sqlite_db, bridge):
        """TC-SP-012: A failed scan carries the error message."""
        db, ws = sqlite_db
        rec = db.create_scan(ws.id, "192.168.1.0/24", "full")
        db.update_scan(rec.id, status=ScanStatus.FAILED, error="nmap: command not found")

        bridge.push_all()

        from apps.scans.models import Scan

        obj = Scan.objects.get(target="192.168.1.0/24")
        assert obj.status == ScanStatus.FAILED
        assert obj.error == "nmap: command not found"

    def test_push_scan_updates_on_resync(self, sqlite_db, bridge):
        """TC-SP-013: A running scan synced early updates to completed on resync."""
        db, ws = sqlite_db
        rec = db.create_scan(ws.id, "10.0.0.0/24", "standard")
        db.update_scan(rec.id, status=ScanStatus.RUNNING, started_at=time.time())

        bridge.push_all()

        db.update_scan(
            rec.id, status=ScanStatus.COMPLETED,
            hosts_up=1, services_found=4, finished_at=time.time(),
        )

        report = bridge.push_all()
        assert report.scans_updated == 1

        from apps.scans.models import Scan

        obj = Scan.objects.get(target="10.0.0.0/24")
        assert obj.status == ScanStatus.COMPLETED
        assert obj.hosts_up == 1


class TestServicePersistence:
    """TC-SP-020 through TC-SP-023: service discovery carries over."""

    def test_push_services_from_scan(self, sqlite_db, bridge):
        """TC-SP-020: Discovered services appear in the dashboard."""
        db, ws = sqlite_db
        scan = db.create_scan(ws.id, "10.10.10.0/24", "standard")
        db.update_scan(scan.id, status=ScanStatus.COMPLETED, hosts_up=1, services_found=2)

        db.add_service(scan.id, host="10.10.10.99", port=22, protocol="tcp",
                       service_name="ssh", product="OpenSSH", version="8.9")
        db.add_service(scan.id, host="10.10.10.99", port=80, protocol="tcp",
                       service_name="http", product="Apache", version="2.4.49")

        report = bridge.push_all()
        assert report.services_pushed == 2

        from apps.scans.models import Service

        services = Service.objects.filter(
            engagement_id=bridge.engagement_id, host="10.10.10.99"
        ).order_by("port")
        assert services.count() == 2
        assert services[0].port == 22
        assert services[0].service_name == "ssh"
        assert services[1].port == 80
        assert services[1].product == "Apache"

    def test_push_services_idempotent(self, sqlite_db, bridge):
        """TC-SP-021: Services are not duplicated on re-push."""
        db, ws = sqlite_db
        scan = db.create_scan(ws.id, "10.10.10.0/24", "quick")
        db.update_scan(scan.id, status=ScanStatus.COMPLETED)
        db.add_service(scan.id, host="10.10.10.99", port=443, protocol="tcp",
                       service_name="https")

        bridge.push_all()
        bridge.push_all()

        from apps.scans.models import Service

        assert Service.objects.filter(host="10.10.10.99", port=443).count() == 1

    def test_push_services_before_scan_errors_gracefully(self, sqlite_db, bridge):
        """TC-SP-022: Services referencing an unsynced scan produce a tracked error."""
        db, ws = sqlite_db
        db.add_service(999, host="10.10.10.1", port=80, protocol="tcp",
                       service_name="http")

        report = bridge.push_all()
        assert len(report.errors) == 1
        assert "hasn't been synced yet" in report.errors[0]

    def test_push_services_multiple_hosts(self, sqlite_db, bridge):
        """TC-SP-023: Services across multiple hosts all sync."""
        db, ws = sqlite_db
        scan = db.create_scan(ws.id, "10.10.10.0/24", "standard")
        db.update_scan(scan.id, status=ScanStatus.COMPLETED, hosts_up=3, services_found=5)

        for host_last_octet in (10, 20, 30):
            db.add_service(scan.id, host=f"10.10.10.{host_last_octet}",
                           port=22, protocol="tcp", service_name="ssh")
        db.add_service(scan.id, host="10.10.10.10", port=80, protocol="tcp",
                       service_name="http")
        db.add_service(scan.id, host="10.10.10.20", port=3306, protocol="tcp",
                       service_name="mysql")

        report = bridge.push_all()
        assert report.services_pushed == 5


# ═══════════════════════════════════════════════════════════════════════
# 2. MODULE INITIALISATION — spec shapes survive the round-trip
# ═══════════════════════════════════════════════════════════════════════


class TestModuleSpecParity:
    """TC-MI-001 through TC-MI-004: each tunnel kind's spec survives sync."""

    SSH_DYNAMIC_SPEC = {
        "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
        "local_bind": "127.0.0.1",
        "local_port": 1080,
    }

    SSH_LOCAL_SPEC = {
        "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
        "local_bind": "127.0.0.1",
        "local_port": 3306,
        "target_host": "10.10.10.50",
        "target_port": 3306,
    }

    SSH_REMOTE_SPEC = {
        "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
        "remote_bind": "0.0.0.0",
        "remote_port": 8080,
        "target_host": "127.0.0.1",
        "target_port": 80,
    }

    SSH_REMOTE_DYNAMIC_SPEC = {
        "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
        "remote_bind": "0.0.0.0",
        "remote_port": 1080,
    }

    @pytest.mark.parametrize("kind,spec", [
        (TunnelKind.SSH_DYNAMIC, SSH_DYNAMIC_SPEC),
        (TunnelKind.SSH_LOCAL, SSH_LOCAL_SPEC),
        (TunnelKind.SSH_REMOTE, SSH_REMOTE_SPEC),
        (TunnelKind.SSH_REMOTE_DYNAMIC, SSH_REMOTE_DYNAMIC_SPEC),
    ], ids=["dynamic", "local", "remote", "remote_dynamic"])
    def test_spec_roundtrip(self, sqlite_db, bridge, kind, spec):
        """TC-MI-001..004: Spec for each tunnel kind is byte-identical after sync."""
        db, ws = sqlite_db
        db.create_tunnel(ws.id, kind, spec, label=f"spec-{kind}")
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label=f"spec-{kind}")
        assert obj.spec == spec
        assert obj.kind == kind


# ═══════════════════════════════════════════════════════════════════════
# 3. SEAMLESS TRANSITION — bidirectional status propagation
# ═══════════════════════════════════════════════════════════════════════


class TestDashboardToCliPull:
    """TC-ST-001 through TC-ST-003: dashboard commands flow to CLI."""

    def test_pull_desired_state_down(self, sqlite_db, bridge):
        """TC-ST-001: Dashboard sets desired_state=down, CLI picks it up."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1085,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="pull-test")
        db.update_tunnel(rec.id, status=TunnelStatus.ACTIVE)

        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="pull-test")
        obj.desired_state = DesiredState.DOWN
        obj.save(update_fields=["desired_state"])

        report = bridge.pull_tunnel_commands()
        assert report.tunnels_pulled == 1

        updated = db.get_tunnel(rec.id)
        assert updated.desired_state == DesiredState.DOWN

    def test_pull_ignores_non_cli_tunnels(self, sqlite_db, bridge):
        """TC-ST-002: Tunnels not created by CLI are not pulled."""
        from apps.tunnels.models import Tunnel

        Tunnel.objects.create(
            engagement_id=bridge.engagement_id,
            kind=TunnelKind.SSH_DYNAMIC,
            label="dashboard-native",
            spec={"endpoint": {"host": "x", "port": 22, "username": "x"},
                  "local_bind": "127.0.0.1", "local_port": 9999},
            owner_engine_id="django-engine",
        )

        report = bridge.pull_tunnel_commands()
        assert report.tunnels_pulled == 0

    def test_full_sync_both_directions(self, sqlite_db, bridge):
        """TC-ST-003: Full sync pushes CLI state and pulls dashboard commands."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1086,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="full-sync")
        db.update_tunnel(rec.id, status=TunnelStatus.ACTIVE)

        report = bridge.sync()

        assert report.tunnels_pushed == 1

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="full-sync")
        obj.desired_state = DesiredState.DOWN
        obj.save(update_fields=["desired_state"])

        report2 = bridge.sync()
        assert report2.tunnels_pulled == 1
        assert report2.tunnels_updated == 1

        updated = db.get_tunnel(rec.id)
        assert updated.desired_state == DesiredState.DOWN


# ═══════════════════════════════════════════════════════════════════════
# 4. EDGE CASES — partial sync, vanished rows, concurrent writes
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """TC-EC-001 through TC-EC-006: resilience and error handling."""

    def test_vanished_dashboard_tunnel(self, sqlite_db, bridge):
        """TC-EC-001: If a dashboard row is deleted, resync logs error but continues."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1087,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="vanish")
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        Tunnel.objects.filter(label="vanish").delete()

        db.update_tunnel(rec.id, status=TunnelStatus.FAILED)
        report = bridge.push_all()

        assert len(report.errors) == 1
        assert "vanished" in report.errors[0]

    def test_empty_database_no_crash(self, sqlite_db, bridge):
        """TC-EC-002: Syncing an empty CLI database produces a clean empty report."""
        report = bridge.push_all()
        assert report.total == 0
        assert not report.errors

    def test_timestamp_conversion(self, sqlite_db, bridge):
        """TC-EC-003: Float epoch timestamps convert to proper datetimes."""
        db, ws = sqlite_db
        now = time.time()
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1088,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="ts-test")
        db.update_tunnel(rec.id, status=TunnelStatus.ACTIVE, started_at=now)

        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="ts-test")
        expected = _epoch_to_datetime(now)
        assert abs((obj.started_at - expected).total_seconds()) < 1.0

    def test_null_timestamps_stay_null(self, sqlite_db, bridge):
        """TC-EC-004: Tunnels that never started have null started_at."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1089,
        }
        db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="null-ts")
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label="null-ts")
        assert obj.started_at is None
        assert obj.stopped_at is None

    def test_special_characters_in_label(self, sqlite_db, bridge):
        """TC-EC-005: Labels with special chars survive the sync."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1091,
        }
        label = "http@10.10.10.99:80 → local (via pivot)"
        db.create_tunnel(ws.id, TunnelKind.SSH_LOCAL, spec, label=label)
        bridge.push_all()

        from apps.tunnels.models import Tunnel

        obj = Tunnel.objects.get(label=label)
        assert obj.label == label

    def test_large_xml_output_survives(self, sqlite_db, bridge):
        """TC-EC-006: Large nmap XML output (>64KB) syncs to dashboard."""
        db, ws = sqlite_db
        scan = db.create_scan(ws.id, "10.0.0.0/16", "full")
        large_xml = "<nmaprun>" + "<host>" * 10000 + "</nmaprun>"
        db.update_scan(scan.id, status=ScanStatus.COMPLETED, xml_output=large_xml)

        bridge.push_all()

        from apps.scans.models import Scan

        obj = Scan.objects.get(target="10.0.0.0/16")
        assert len(obj.raw_stdout) == len(large_xml)


# ═══════════════════════════════════════════════════════════════════════
# 5. WORKSPACE ↔ ENGAGEMENT MAPPING
# ═══════════════════════════════════════════════════════════════════════


class TestWorkspaceEngagementMapping:
    """TC-WE-001 through TC-WE-003: workspace isolation in sync."""

    def test_only_specified_workspace_syncs(self, sqlite_db, engagement):
        """TC-WE-001: Only tunnels from the specified workspace are pushed."""
        db, ws = sqlite_db
        ws2 = db.create_workspace("other-project")

        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1092,
        }
        db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="ws1-tunnel")
        db.create_tunnel(ws2.id, TunnelKind.SSH_DYNAMIC, spec, label="ws2-tunnel")

        bridge = SyncBridge(db, engagement.pk, workspace_id=ws.id)
        report = bridge.push_all()

        assert report.tunnels_pushed == 1

        from apps.tunnels.models import Tunnel

        assert Tunnel.objects.filter(label="ws1-tunnel").exists()
        assert not Tunnel.objects.filter(label="ws2-tunnel").exists()

    def test_all_workspaces_when_none_specified(self, sqlite_db, engagement):
        """TC-WE-002: When workspace_id is None, all workspaces sync."""
        db, ws = sqlite_db
        ws2 = db.create_workspace("project-b")

        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1093,
        }
        db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec, label="all-ws-1")
        db.create_tunnel(ws2.id, TunnelKind.SSH_DYNAMIC, spec, label="all-ws-2")

        bridge = SyncBridge(db, engagement.pk, workspace_id=None)
        report = bridge.push_all()

        assert report.tunnels_pushed == 2


# ═══════════════════════════════════════════════════════════════════════
# 6. SYNC STATE TABLE INTEGRITY
# ═══════════════════════════════════════════════════════════════════════


class TestSyncStateIntegrity:
    """TC-SS-001 through TC-SS-003: the sync_state tracking table."""

    def test_sync_state_tracks_mapping(self, sqlite_db, bridge):
        """TC-SS-001: After push, sync_state maps local_id to remote_id."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1094,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec)
        bridge.push_all()

        remote_id = bridge._get_remote_id("tunnel", rec.id)
        assert remote_id is not None

        from apps.tunnels.models import Tunnel

        assert Tunnel.objects.filter(pk=remote_id).exists()

    def test_sync_state_bidirectional_lookup(self, sqlite_db, bridge):
        """TC-SS-002: Can look up local_id from remote_id and vice versa."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1095,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec)
        bridge.push_all()

        remote_id = bridge._get_remote_id("tunnel", rec.id)
        local_id = bridge._get_local_id("tunnel", remote_id)
        assert local_id == rec.id

    def test_sync_state_survives_db_reopen(self, sqlite_db, bridge):
        """TC-SS-003: Sync state persists across StateDB reopen."""
        db, ws = sqlite_db
        spec = {
            "endpoint": {"host": "10.10.10.99", "port": 22, "username": "root"},
            "local_bind": "127.0.0.1",
            "local_port": 1096,
        }
        rec = db.create_tunnel(ws.id, TunnelKind.SSH_DYNAMIC, spec)
        bridge.push_all()

        db2 = StateDB(db.db_path)
        bridge2 = SyncBridge(db2, bridge.engagement_id, workspace_id=ws.id)

        remote_id = bridge2._get_remote_id("tunnel", rec.id)
        assert remote_id is not None
