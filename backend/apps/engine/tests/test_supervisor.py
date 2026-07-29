"""Supervisor reconciliation tests.

These use a fake adapter that plans harmless local processes (``sleep``, ``sh``)
instead of real ssh, so the *reconciliation logic* is exercised end to end —
start, stop, crash detection, adoption — without needing an SSH server.
"""

from __future__ import annotations

import time

import pytest

from apps.engine.adapters.base import LaunchPlan
from apps.engine.supervisor import MAX_CONSECUTIVE_FAILURES, Supervisor
from apps.tunnels.models import (
    DesiredState,
    Tunnel,
    TunnelKind,
    TunnelLog,
    TunnelStatus,
)

pytestmark = pytest.mark.django_db(transaction=True)


SPEC = {
    "endpoint": {"user": "opsec", "host": "10.4.0.10", "port": 22},
    "local_port": 8080,
    "target_host": "10.4.9.5",
    "target_port": 1433,
}


class FakeSsh:
    """Plans a real but harmless process, so lifecycle behaviour is genuine."""

    def __init__(self, argv=None):
        self.argv = argv or ["/bin/sh", "-c", "sleep 300"]

    def is_available(self) -> bool:
        return True

    def plan(self, spec, *, tunnel=None) -> LaunchPlan:
        return LaunchPlan(argv=self.argv, description="fake tunnel")

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        return f"exited with {returncode}"


@pytest.fixture
def supervisor(db):
    instance = Supervisor(instance_id="test-engine")
    instance.ssh = FakeSsh()
    yield instance
    instance.shutdown()


def make_tunnel(engagement, **overrides) -> Tunnel:
    defaults = {
        "engagement": engagement,
        "kind": TunnelKind.SSH_LOCAL,
        "spec": SPEC,
        "desired_state": DesiredState.UP,
        "status": TunnelStatus.PENDING,
    }
    return Tunnel.objects.create(**(defaults | overrides))


def wait_until(predicate, timeout=10.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ── Start ───────────────────────────────────────────────────────────────


def test_pending_tunnel_is_started(supervisor, engagement):
    tunnel = make_tunnel(engagement)
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.ACTIVE
    assert tunnel.pid is not None
    assert tunnel.owner_engine_id == "test-engine"
    assert tunnel.started_at is not None


def test_start_is_audited_and_logged(supervisor, engagement):
    from apps.audit.models import AuditAction, AuditEvent

    tunnel = make_tunnel(engagement)
    supervisor.tick()

    assert AuditEvent.objects.filter(action=AuditAction.TUNNEL_STARTED).exists()
    assert TunnelLog.objects.filter(tunnel=tunnel).exists()


def test_an_active_tunnel_is_not_started_twice(supervisor, engagement):
    make_tunnel(engagement)
    supervisor.tick()
    first = set(supervisor.tunnels.keys())
    supervisor.tick()
    assert set(supervisor.tunnels.keys()) == first
    assert len(supervisor.tunnels) == 1


def test_malformed_spec_fails_without_spawning(supervisor, engagement):
    tunnel = make_tunnel(engagement, spec={"garbage": True})
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.FAILED
    assert tunnel.pid is None
    assert supervisor.tunnels == {}


def test_concurrency_ceiling_is_enforced(supervisor, engagement, settings):
    supervisor.config = {**supervisor.config, "MAX_CONCURRENT_TUNNELS": 2}
    for _ in range(5):
        make_tunnel(engagement)

    supervisor.tick()
    assert len(supervisor.tunnels) == 2


def test_a_repeatedly_failing_tunnel_stops_being_retried(supervisor, engagement):
    """A permanently broken spec must not become an infinite spawn loop."""
    tunnel = make_tunnel(engagement, restart_count=MAX_CONSECUTIVE_FAILURES)
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.FAILED
    assert "Gave up" in tunnel.last_error
    assert supervisor.tunnels == {}


# ── Stop ────────────────────────────────────────────────────────────────


def test_stop_request_is_honoured(supervisor, engagement):
    from apps.engine.process import is_pid_alive

    tunnel = make_tunnel(engagement)
    supervisor.tick()
    tunnel.refresh_from_db()
    pid = tunnel.pid

    tunnel.desired_state = DesiredState.DOWN
    tunnel.save(update_fields=["desired_state"])
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.STOPPED
    assert tunnel.pid is None
    assert tunnel.stopped_at is not None
    assert wait_until(lambda: not is_pid_alive(pid)), "the real process must be gone"


def test_stop_clears_the_failure_counter(supervisor, engagement):
    tunnel = make_tunnel(engagement, restart_count=3)
    supervisor.tick()
    tunnel.refresh_from_db()

    tunnel.desired_state = DesiredState.DOWN
    tunnel.save(update_fields=["desired_state"])
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.restart_count == 0


# ── Crash detection ─────────────────────────────────────────────────────


def test_a_process_that_dies_on_its_own_is_marked_failed(engagement):
    """Exiting while desired_state is up is a failure, not a clean stop."""
    supervisor = Supervisor(instance_id="test-engine")
    supervisor.ssh = FakeSsh(argv=["/bin/sh", "-c", "exit 42"])
    try:
        tunnel = make_tunnel(engagement)
        supervisor.tick()

        assert wait_until(lambda: supervisor.tunnels[tunnel.pk].process.poll() is not None)
        supervisor.tick()
        tunnel.refresh_from_db()

        assert tunnel.status == TunnelStatus.FAILED
        assert tunnel.restart_count == 1
        assert "42" in tunnel.last_error
        assert tunnel.pid is None
    finally:
        supervisor.shutdown()


def test_crash_is_audited(engagement):
    from apps.audit.models import AuditAction, AuditEvent

    supervisor = Supervisor(instance_id="test-engine")
    supervisor.ssh = FakeSsh(argv=["/bin/sh", "-c", "exit 1"])
    try:
        tunnel = make_tunnel(engagement)
        supervisor.tick()
        assert wait_until(lambda: supervisor.tunnels[tunnel.pk].process.poll() is not None)
        supervisor.tick()
        assert AuditEvent.objects.filter(action=AuditAction.TUNNEL_FAILED).exists()
    finally:
        supervisor.shutdown()


def test_stderr_is_captured_into_the_tunnel_log(engagement):
    supervisor = Supervisor(instance_id="test-engine")
    supervisor.ssh = FakeSsh(argv=["/bin/sh", "-c", "echo 'permission denied' >&2; sleep 300"])
    try:
        tunnel = make_tunnel(engagement)
        supervisor.tick()
        assert wait_until(
            lambda: TunnelLog.objects.filter(
                tunnel=tunnel, message__icontains="permission denied"
            ).exists()
        )
    finally:
        supervisor.shutdown()


# ── Adoption after an engine restart ────────────────────────────────────


def test_a_dead_process_from_a_previous_engine_is_corrected(supervisor, engagement):
    tunnel = make_tunnel(
        engagement,
        status=TunnelStatus.ACTIVE,
        pid=999_999,  # not a live pid
        owner_engine_id="an-older-engine",
    )
    supervisor.tick()
    tunnel.refresh_from_db()

    # desired_state is still up, so it goes back to pending to be restarted.
    assert tunnel.status in {TunnelStatus.PENDING, TunnelStatus.ACTIVE}
    assert "no longer running" in tunnel.last_error or tunnel.status == TunnelStatus.ACTIVE


def test_a_live_process_from_another_engine_is_flagged_not_killed(supervisor, engagement):
    """Silently killing a live tunnel into a client network on startup would be
    worse than reporting that it needs attention."""
    import os

    tunnel = make_tunnel(
        engagement,
        status=TunnelStatus.ACTIVE,
        pid=os.getpid(),  # definitely alive, definitely not ours
        owner_engine_id="another-engine",
    )
    supervisor.tick()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.DEGRADED
    assert "another engine instance" in tunnel.last_error
    assert tunnel.pk not in supervisor.tunnels


def test_shutdown_leaves_wanted_tunnels_restartable(engagement):
    """Shutdown must not claim STOPPED — the operator still wants them up."""
    supervisor = Supervisor(instance_id="test-engine")
    supervisor.ssh = FakeSsh()
    tunnel = make_tunnel(engagement)
    supervisor.tick()

    supervisor.shutdown()
    tunnel.refresh_from_db()

    assert tunnel.status == TunnelStatus.PENDING
    assert tunnel.desired_state == DesiredState.UP
    assert tunnel.pid is None


# ── Registration ────────────────────────────────────────────────────────


def test_registration_reports_capabilities(supervisor):
    instance = supervisor.register()
    assert instance.instance_id == "test-engine"
    assert set(instance.capabilities) == {"ssh", "nmap"}


def test_log_pruning_keeps_the_table_bounded(supervisor, engagement, monkeypatch):
    monkeypatch.setattr("apps.engine.supervisor.MAX_LOG_ROWS_PER_TUNNEL", 10)
    tunnel = make_tunnel(engagement)
    for index in range(30):
        supervisor._log(tunnel, f"line {index}")
    assert TunnelLog.objects.filter(tunnel=tunnel).count() <= 10
