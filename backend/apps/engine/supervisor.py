"""The reconciler.

The web tier records what an operator *wants*; this loop makes reality match,
and writes back what actually *is*. Keeping those two directions separate is
what lets Django restart, redeploy or crash without disturbing a live tunnel,
and lets the engine restart and re-adopt rather than orphan.

Each pass:

1. Adopt or disown processes recorded by a previous engine run.
2. Start tunnels whose desired state is up but which are not running.
3. Stop tunnels whose desired state is down but which still are.
4. Notice processes that died on their own and record why.
5. Run queued scans.
6. Heartbeat, so the dashboard can say whether a control plane is attached.

Every state change is written to the database and broadcast, so the dashboard
and the CLI observe the same truth.
"""

from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.api import broadcast
from apps.audit.context import AuditContext, using
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.engine.models import EngineInstance
from apps.scans import services as scan_services
from apps.scans.models import Scan, ScanStatus
from apps.scans.parsers import NmapParseError, parse_nmap_xml
from apps.tunnels.models import (
    LIVE_STATUSES,
    DesiredState,
    Tunnel,
    TunnelKind,
    TunnelLog,
    TunnelLogLevel,
    TunnelStatus,
)
from mudale import __version__ as VERSION
from mudale_engine.adapters.base import AdapterUnavailable
from mudale_engine.adapters.nmap import NmapAdapter
from mudale_engine.adapters.ssh import SshAdapter
from mudale_engine.process import SupervisedProcess, is_pid_alive
from mudale_engine.specs import SpecError, parse_spec

logger = logging.getLogger(__name__)


#: Keep at most this many log lines per tunnel in the database. The engine
#: prunes on write so a chatty process cannot grow the table without bound —
#: v2 kept scan output and tunnel logs in memory forever.
MAX_LOG_ROWS_PER_TUNNEL = 1000

#: A tunnel that fails this many times in a row stops being retried, so a
#: permanently broken spec cannot become an infinite spawn loop.
MAX_CONSECUTIVE_FAILURES = 5

SSH_KINDS = frozenset(
    {
        TunnelKind.SSH_LOCAL,
        TunnelKind.SSH_DYNAMIC,
        TunnelKind.SSH_REMOTE,
        TunnelKind.SSH_REMOTE_DYNAMIC,
    }
)


@dataclass
class RunningTunnel:
    tunnel_id: int
    process: SupervisedProcess
    started_at: float = field(default_factory=time.monotonic)


@dataclass
class RunningScan:
    scan_id: int
    process: SupervisedProcess
    started_at: float = field(default_factory=time.monotonic)
    cleanup_files: list[str] = field(default_factory=list)


class Supervisor:
    """Owns every process this engine instance started."""

    def __init__(self, *, instance_id: str | None = None):
        self.instance_id = instance_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.config = settings.ENGINE

        state_dir = self.config["LOG_DIR"]
        self.ssh = SshAdapter(self.config["SSH_BIN"], state_dir=state_dir)
        self.nmap = NmapAdapter(self.config["NMAP_BIN"], state_dir=state_dir)

        self.tunnels: dict[int, RunningTunnel] = {}
        self.scans: dict[int, RunningScan] = {}
        self._stopping = False

    # ── Lifecycle ───────────────────────────────────────────────────────

    def capabilities(self) -> dict:
        return {
            "ssh": self.ssh.is_available(),
            "nmap": self.nmap.is_available(),
            # Without proxychains, scans can still run — but not *through* a
            # pivot, so the dashboard needs to know.
            "pivot_scanning": self.nmap.can_scan_through_a_pivot(),
        }

    def register(self) -> EngineInstance:
        capabilities = self.capabilities()
        instance, _ = EngineInstance.objects.update_or_create(
            instance_id=self.instance_id,
            defaults={
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "version": VERSION,
                "capabilities": capabilities,
                "stopped_at": None,
            },
        )
        logger.info(
            "Engine %s registered (ssh=%s nmap=%s pivot_scanning=%s)",
            self.instance_id,
            capabilities["ssh"],
            capabilities["nmap"],
            capabilities["pivot_scanning"],
        )
        return instance

    def heartbeat(self) -> None:
        EngineInstance.objects.filter(instance_id=self.instance_id).update(
            last_heartbeat_at=timezone.now()
        )

    def shutdown(self) -> None:
        """Stop supervising, leaving the database honest about what happened.

        Tunnels are marked PENDING rather than STOPPED: their desired state is
        still up, and another engine (or this one, restarted) should bring them
        back. Claiming STOPPED would make the dashboard assert something the
        operator did not ask for.
        """
        self._stopping = True
        grace = float(self.config["STOP_GRACE_SECONDS"])

        for running in list(self.tunnels.values()):
            try:
                running.process.stop(grace_seconds=grace)
            except Exception:
                logger.exception("Error stopping tunnel %s", running.tunnel_id)
            Tunnel.objects.filter(pk=running.tunnel_id).update(
                status=TunnelStatus.PENDING, pid=None, owner_engine_id=""
            )

        for running in list(self.scans.values()):
            try:
                running.process.stop(grace_seconds=grace)
            except Exception:
                logger.exception("Error stopping scan %s", running.scan_id)
            Scan.objects.filter(pk=running.scan_id).update(
                status=ScanStatus.QUEUED, pid=None, owner_engine_id=""
            )

        EngineInstance.objects.filter(instance_id=self.instance_id).update(
            stopped_at=timezone.now()
        )
        logger.info("Engine %s shut down", self.instance_id)

    # ── Main loop ───────────────────────────────────────────────────────

    def tick(self) -> None:
        """One reconciliation pass. Never raises — a bad row must not kill the loop."""
        close_old_connections()

        with using(AuditContext()):  # engine actions are attributed to "system"
            self._adopt_orphans()
            self._reap_finished_tunnels()
            self._start_wanted_tunnels()
            self._stop_unwanted_tunnels()
            self._reap_finished_scans()
            self._start_queued_scans()
            self.heartbeat()

    # ── Adoption ────────────────────────────────────────────────────────

    def _adopt_orphans(self) -> None:
        """Handle rows left behind by a previous engine run.

        A process this instance did not start cannot be supervised — we have no
        pipe to it and cannot latch its exit. If its PID is gone, the row is
        corrected to reflect that. If it is still alive but unmanaged, it is
        marked DEGRADED and left alone rather than killed: silently terminating
        a live tunnel into a client network on startup would be worse than
        reporting that it needs attention.
        """
        stale = (
            Tunnel.objects.filter(status__in=LIVE_STATUSES)
            .exclude(owner_engine_id=self.instance_id)
            .select_related("engagement")
        )
        for tunnel in stale:
            if not tunnel.engagement.is_operational:
                # Not ours to reconcile. Leaving the row as it stands is also
                # what makes an archived engagement readable after the fact.
                continue
            if tunnel.pid and is_pid_alive(tunnel.pid):
                if tunnel.status != TunnelStatus.DEGRADED:
                    self._set_status(
                        tunnel,
                        TunnelStatus.DEGRADED,
                        error=(
                            f"Process {tunnel.pid} is running but was started by another "
                            f"engine instance ({tunnel.owner_engine_id or 'unknown'}), so it "
                            f"cannot be supervised from here. Stop it to hand control over."
                        ),
                    )
            else:
                self._set_status(
                    tunnel,
                    TunnelStatus.PENDING if tunnel.desired_state == DesiredState.UP
                    else TunnelStatus.STOPPED,
                    error="Process is gone; the engine that started it is no longer running.",
                    pid=None,
                )

        Scan.objects.filter(status=ScanStatus.RUNNING).exclude(
            owner_engine_id=self.instance_id
        ).update(status=ScanStatus.QUEUED, pid=None, owner_engine_id="")

    # ── Tunnels ─────────────────────────────────────────────────────────

    def _start_wanted_tunnels(self) -> None:
        if self._stopping:
            return

        capacity = int(self.config["MAX_CONCURRENT_TUNNELS"]) - len(self.tunnels)
        if capacity <= 0:
            return

        # Only act for engagements that are actually operational. A paused,
        # closed or out-of-window engagement authorises nothing, and starting a
        # tunnel for one would route traffic into a client network the team is
        # no longer permitted to touch.
        wanted = [
            tunnel
            for tunnel in Tunnel.objects.filter(
                desired_state=DesiredState.UP,
                status__in=[TunnelStatus.PENDING],
            )
            .exclude(pk__in=self.tunnels.keys())
            .select_related("engagement")[: capacity * 4]
            if tunnel.engagement.is_operational
        ][:capacity]

        for tunnel in wanted:
            self._start_tunnel(tunnel)

    def _start_tunnel(self, tunnel: Tunnel) -> None:
        if tunnel.restart_count >= MAX_CONSECUTIVE_FAILURES:
            self._set_status(
                tunnel,
                TunnelStatus.FAILED,
                error=(
                    f"Gave up after {tunnel.restart_count} consecutive failures. "
                    f"Fix the cause, then start it again."
                ),
            )
            return

        try:
            spec = parse_spec(tunnel.kind, tunnel.spec)
        except SpecError as exc:
            self._set_status(tunnel, TunnelStatus.FAILED, error=str(exc))
            return

        if tunnel.kind not in SSH_KINDS:
            self._set_status(
                tunnel,
                TunnelStatus.FAILED,
                error=f"No adapter is available for {tunnel.get_kind_display()} yet.",
            )
            return

        try:
            plan = self.ssh.plan(spec, tunnel=tunnel)
        except AdapterUnavailable as exc:
            self._set_status(tunnel, TunnelStatus.FAILED, error=str(exc))
            return

        self._set_status(tunnel, TunnelStatus.STARTING)
        self._log(tunnel, f"Starting: {plan.description}")

        process = SupervisedProcess(
            argv=plan.argv,
            env=plan.env,
            description=plan.description,
            on_output=lambda stream, line, tid=tunnel.pk: self._on_output(tid, stream, line),
        )

        try:
            pid = process.start()
        except OSError as exc:
            self._set_status(
                tunnel, TunnelStatus.FAILED, error=f"Could not start process: {exc}"
            )
            return

        self.tunnels[tunnel.pk] = RunningTunnel(tunnel_id=tunnel.pk, process=process)

        tunnel.pid = pid
        tunnel.owner_engine_id = self.instance_id
        tunnel.started_at = timezone.now()
        tunnel.stopped_at = None
        tunnel.status = TunnelStatus.ACTIVE
        tunnel.last_error = ""
        tunnel.save(
            update_fields=[
                "pid", "owner_engine_id", "started_at", "stopped_at",
                "status", "last_error", "updated_at",
            ]
        )

        record(
            AuditAction.TUNNEL_STARTED,
            engagement=tunnel.engagement,
            obj=tunnel,
            message=plan.description,
            payload={"pid": pid},
        )
        self._log(tunnel, f"Active (pid {pid})")
        broadcast.tunnel_updated(tunnel)

    def _stop_unwanted_tunnels(self) -> None:
        grace = float(self.config["STOP_GRACE_SECONDS"])

        for tunnel in Tunnel.objects.filter(
            desired_state=DesiredState.DOWN, status__in=LIVE_STATUSES
        ):
            running = self.tunnels.get(tunnel.pk)
            if running is None:
                # Not ours to stop — adoption already explained why.
                if tunnel.pid and is_pid_alive(tunnel.pid):
                    continue
                self._set_status(tunnel, TunnelStatus.STOPPED, pid=None)
                continue

            self._set_status(tunnel, TunnelStatus.STOPPING)
            self._log(tunnel, "Stopping")

            try:
                running.process.stop(grace_seconds=grace)
            except Exception as exc:
                logger.exception("Error stopping tunnel %s", tunnel.pk)
                self._set_status(tunnel, TunnelStatus.FAILED, error=str(exc))
                self.tunnels.pop(tunnel.pk, None)
                continue

            self.tunnels.pop(tunnel.pk, None)
            tunnel.status = TunnelStatus.STOPPED
            tunnel.stopped_at = timezone.now()
            tunnel.pid = None
            tunnel.owner_engine_id = ""
            tunnel.restart_count = 0
            tunnel.save(
                update_fields=[
                    "status", "stopped_at", "pid", "owner_engine_id",
                    "restart_count", "updated_at",
                ]
            )
            self._log(tunnel, "Stopped")
            broadcast.tunnel_updated(tunnel)

    def _reap_finished_tunnels(self) -> None:
        """Notice processes that exited without being asked to."""
        for tunnel_id, running in list(self.tunnels.items()):
            outcome = running.process.poll()
            if outcome is None:
                continue

            self.tunnels.pop(tunnel_id, None)

            tunnel = Tunnel.objects.filter(pk=tunnel_id).select_related("engagement").first()
            if tunnel is None:
                continue

            explanation = self.ssh.interpret_exit(outcome.returncode, outcome.stderr_tail)

            if tunnel.desired_state == DesiredState.DOWN or outcome.requested:
                tunnel.status = TunnelStatus.STOPPED
                tunnel.restart_count = 0
            else:
                # Died on its own while it was supposed to be up.
                tunnel.status = TunnelStatus.FAILED
                tunnel.restart_count += 1
                record(
                    AuditAction.TUNNEL_FAILED,
                    result="error",
                    engagement=tunnel.engagement,
                    obj=tunnel,
                    message=explanation,
                )

            tunnel.pid = None
            tunnel.owner_engine_id = ""
            tunnel.stopped_at = timezone.now()
            tunnel.last_error = explanation if tunnel.status == TunnelStatus.FAILED else ""
            tunnel.save(
                update_fields=[
                    "status", "restart_count", "pid", "owner_engine_id",
                    "stopped_at", "last_error", "updated_at",
                ]
            )
            self._log(
                tunnel,
                explanation,
                level=(
                    TunnelLogLevel.ERROR
                    if tunnel.status == TunnelStatus.FAILED
                    else TunnelLogLevel.INFO
                ),
            )
            broadcast.tunnel_updated(tunnel)

    # ── Scans ───────────────────────────────────────────────────────────

    def _start_queued_scans(self) -> None:
        if self._stopping or not self.nmap.is_available():
            return

        for scan in Scan.objects.filter(status=ScanStatus.QUEUED).exclude(
            pk__in=self.scans.keys()
        )[:4]:
            self._start_scan(scan)

    def _start_scan(self, scan: Scan) -> None:
        import ipaddress

        try:
            # The stored target was normalised from a parsed network at request
            # time; re-parsing here keeps the adapter's type contract honest.
            target = ipaddress.ip_network(scan.target, strict=False)
        except ValueError as exc:
            scan_services.mark_failed(scan, f"Stored target is not a network: {exc}")
            broadcast.scan_updated(scan)
            return

        socks = self._socks_for(scan)
        if scan.via_tunnel_id is not None and socks is None:
            # Refuse rather than quietly scan from the wrong vantage point. A
            # result labelled "through the pivot" that actually came from the
            # engine host is worse than no result: it becomes a false claim in
            # the reachability map and in the report.
            scan_services.mark_failed(
                scan,
                "The scan was requested through a tunnel that is not a live SOCKS proxy, "
                "so it cannot be routed. Start the pivot and try again.",
            )
            broadcast.scan_updated(scan)
            return

        try:
            plan = self.nmap.plan(target=target, profile=scan.profile, socks=socks)
        except AdapterUnavailable as exc:
            scan_services.mark_failed(scan, str(exc))
            broadcast.scan_updated(scan)
            return
        process = SupervisedProcess(
            argv=plan.argv, env=plan.env, description=plan.description, log_lines=20000
        )

        try:
            pid = process.start()
        except OSError as exc:
            scan_services.mark_failed(scan, f"Could not start nmap: {exc}")
            broadcast.scan_updated(scan)
            return

        self.scans[scan.pk] = RunningScan(
            scan_id=scan.pk, process=process, cleanup_files=plan.cleanup_files,
        )

        scan.status = ScanStatus.RUNNING
        scan.pid = pid
        scan.owner_engine_id = self.instance_id
        scan.started_at = timezone.now()
        scan.save(update_fields=["status", "pid", "owner_engine_id", "started_at"])
        broadcast.scan_updated(scan)
        logger.info("Scan %s started: %s", scan.pk, plan.description)

    def _socks_for(self, scan: Scan) -> tuple[str, int] | None:
        """The SOCKS endpoint to route this scan through, if it asked for one."""
        if scan.via_tunnel_id is None:
            return None

        tunnel = Tunnel.objects.filter(pk=scan.via_tunnel_id).first()
        if tunnel is None or tunnel.kind != TunnelKind.SSH_DYNAMIC:
            return None
        if tunnel.status != TunnelStatus.ACTIVE:
            return None

        bind = tunnel.spec.get("local_bind", "127.0.0.1")
        port = tunnel.spec.get("local_port")
        if not isinstance(port, int):
            return None
        return (bind, port)

    def _reap_finished_scans(self) -> None:
        timeout = float(self.config["SCAN_TIMEOUT_SECONDS"])

        for scan_id, running in list(self.scans.items()):
            if time.monotonic() - running.started_at > timeout:
                running.process.stop(grace_seconds=5)
                self.scans.pop(scan_id, None)
                for path in running.cleanup_files:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                scan = Scan.objects.filter(pk=scan_id).first()
                if scan:
                    scan_services.mark_failed(
                        scan,
                        f"Scan exceeded the {timeout:.0f}s limit and was stopped.",
                        status=ScanStatus.TIMED_OUT,
                    )
                    broadcast.scan_updated(scan)
                continue

            outcome = running.process.poll()
            if outcome is None:
                continue

            self.scans.pop(scan_id, None)
            for path in running.cleanup_files:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            scan = Scan.objects.filter(pk=scan_id).select_related("engagement").first()
            if scan is None:
                continue

            scan.exit_code = outcome.returncode
            scan.raw_stderr = outcome.stderr_tail[-8000:]
            scan.pid = None
            scan.save(update_fields=["exit_code", "raw_stderr", "pid"])

            if outcome.returncode != 0:
                scan_services.mark_failed(
                    scan, self.nmap.interpret_exit(outcome.returncode, outcome.stderr_tail)
                )
                broadcast.scan_updated(scan)
                continue

            try:
                parsed = parse_nmap_xml(outcome.stdout_tail)
            except NmapParseError as exc:
                # An unparseable document is a failure, not an empty result —
                # v2 reported this case as a successful scan that found nothing.
                scan_services.mark_failed(scan, str(exc))
                broadcast.scan_updated(scan)
                continue

            scan_services.ingest_results(scan, parsed, raw_xml=outcome.stdout_tail[:200_000])
            scan.refresh_from_db()
            broadcast.scan_updated(scan)
            logger.info("Scan %s finished: %s services", scan.pk, scan.services_found)

    # ── Helpers ─────────────────────────────────────────────────────────

    def _set_status(
        self, tunnel: Tunnel, status: str, *, error: str = "", pid: int | None = ...
    ) -> None:
        fields = ["status", "updated_at"]
        tunnel.status = status
        if error:
            tunnel.last_error = error
            fields.append("last_error")
        if pid is not ...:
            tunnel.pid = pid
            fields.append("pid")
        tunnel.save(update_fields=fields)
        if error:
            self._log(tunnel, error, level=TunnelLogLevel.ERROR)
        broadcast.tunnel_updated(tunnel)

    def _on_output(self, tunnel_id: int, stream: str, line: str) -> None:
        """Called from a reader thread, so it must open its own connection."""
        close_old_connections()
        tunnel = Tunnel.objects.filter(pk=tunnel_id).first()
        if tunnel is None:
            return
        level = TunnelLogLevel.ERROR if stream == "stderr" else TunnelLogLevel.INFO
        self._log(tunnel, line, level=level, source=stream)

    def _log(
        self,
        tunnel: Tunnel,
        message: str,
        *,
        level: str = TunnelLogLevel.INFO,
        source: str = "engine",
    ) -> None:
        entry = TunnelLog.objects.create(
            tunnel=tunnel, message=message[:4000], level=level, source=source
        )
        self._prune_logs(tunnel)
        broadcast.tunnel_log(tunnel, entry)

    @staticmethod
    def _prune_logs(tunnel: Tunnel) -> None:
        """Keep the log table bounded per tunnel."""
        count = TunnelLog.objects.filter(tunnel=tunnel).count()
        if count <= MAX_LOG_ROWS_PER_TUNNEL:
            return
        cutoff_ids = list(
            TunnelLog.objects.filter(tunnel=tunnel)
            .order_by("-created_at", "-id")
            .values_list("id", flat=True)[MAX_LOG_ROWS_PER_TUNNEL:]
        )
        TunnelLog.objects.filter(id__in=cutoff_ids).delete()
