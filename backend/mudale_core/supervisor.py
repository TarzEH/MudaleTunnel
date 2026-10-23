"""Standalone reconciler — no Django.

Manages tunnel and scan processes using SQLite state. The supervisor loop:
1. Start tunnels whose desired state is up but not running
2. Stop tunnels whose desired state is down but still running
3. Notice processes that died and record why
4. Run queued scans
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mudale_core.state import StateDB
from mudale_engine.adapters.nmap import NmapAdapter
from mudale_engine.adapters.ssh import SshAdapter
from mudale_engine.enums import (
    DesiredState,
    ScanStatus,
    TunnelStatus,
)
from mudale_engine.process import SupervisedProcess, is_pid_alive
from mudale_engine.specs import SpecError, parse_spec

logger = logging.getLogger(__name__)


@dataclass
class RunningTunnel:
    tunnel_id: int
    process: SupervisedProcess


@dataclass
class RunningScan:
    scan_id: int
    process: SupervisedProcess
    cleanup_files: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    timeout: float = 600.0


class Engine:
    """Standalone tunnel/scan engine backed by SQLite."""

    def __init__(
        self,
        db: StateDB | None = None,
        state_dir: str | Path | None = None,
        on_tunnel_change: Callable[[int, str], None] | None = None,
        on_scan_change: Callable[[int, str], None] | None = None,
    ):
        self._state_dir = Path(state_dir) if state_dir else Path.home() / ".mudale"
        self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = db or StateDB(self._state_dir / "mudale.db")
        self._tunnels: dict[int, RunningTunnel] = {}
        self._scans: dict[int, RunningScan] = {}
        self._on_tunnel_change = on_tunnel_change
        self._on_scan_change = on_scan_change

        self.ssh = SshAdapter("ssh", state_dir=self._state_dir)
        self.nmap = NmapAdapter("nmap", state_dir=self._state_dir)

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "ssh": self.ssh.is_available(),
            "nmap": self.nmap.is_available(),
            "pivot_scanning": (
                self.nmap.can_scan_through_a_pivot() if self.nmap.is_available() else False
            ),
        }

    # ── Tunnel operations ──────────────────────────────────────────────

    def start_tunnel(self, tunnel_id: int) -> bool:
        rec = self.db.get_tunnel(tunnel_id)
        if rec is None:
            logger.error("Tunnel %d not found", tunnel_id)
            return False

        if tunnel_id in self._tunnels:
            logger.warning("Tunnel %d already has a running process", tunnel_id)
            return True

        try:
            spec = parse_spec(rec.kind, rec.spec)
        except SpecError as exc:
            self._fail_tunnel(tunnel_id, str(exc))
            return False

        plan = self.ssh.plan(spec)

        proc = SupervisedProcess(
            argv=plan.argv,
            env=plan.env,
            description=plan.description,
            log_lines=500,
        )

        self.db.update_tunnel(tunnel_id, status=TunnelStatus.STARTING)
        self._notify_tunnel(tunnel_id, TunnelStatus.STARTING)

        try:
            pid = proc.start()
        except OSError as exc:
            self._fail_tunnel(tunnel_id, f"Failed to start: {exc}")
            return False

        self.db.update_tunnel(tunnel_id, pid=pid, started_at=time.time())
        self._tunnels[tunnel_id] = RunningTunnel(tunnel_id=tunnel_id, process=proc)

        time.sleep(min(plan.startup_timeout, 2.0))

        outcome = proc.poll()
        if outcome is not None:
            error = self.ssh.interpret_exit(outcome.returncode, outcome.stderr_tail)
            self._fail_tunnel(tunnel_id, error)
            del self._tunnels[tunnel_id]
            return False

        self.db.update_tunnel(tunnel_id, status=TunnelStatus.ACTIVE)
        self._notify_tunnel(tunnel_id, TunnelStatus.ACTIVE)
        return True

    def stop_tunnel(self, tunnel_id: int) -> bool:
        from mudale_engine.process import kill_process_group

        self.db.update_tunnel(tunnel_id, desired_state=DesiredState.DOWN)
        rt = self._tunnels.get(tunnel_id)

        if rt is not None:
            self.db.update_tunnel(tunnel_id, status=TunnelStatus.STOPPING)
            self._notify_tunnel(tunnel_id, TunnelStatus.STOPPING)
            rt.process.stop(grace_seconds=10.0)
            del self._tunnels[tunnel_id]
        else:
            rec = self.db.get_tunnel(tunnel_id)
            if rec and rec.pid and is_pid_alive(rec.pid):
                self.db.update_tunnel(tunnel_id, status=TunnelStatus.STOPPING)
                self._notify_tunnel(tunnel_id, TunnelStatus.STOPPING)
                kill_process_group(rec.pid, grace_seconds=10.0)

        self.db.update_tunnel(
            tunnel_id, status=TunnelStatus.STOPPED, pid=None, stopped_at=time.time()
        )
        self._notify_tunnel(tunnel_id, TunnelStatus.STOPPED)
        return True

    def reap_tunnels(self) -> list[int]:
        """Check for tunnels that died on their own."""
        reaped = []
        for tid, rt in list(self._tunnels.items()):
            outcome = rt.process.poll()
            if outcome is not None:
                error = self.ssh.interpret_exit(outcome.returncode, outcome.stderr_tail)
                if outcome.requested:
                    self.db.update_tunnel(
                        tid, status=TunnelStatus.STOPPED, pid=None, stopped_at=time.time()
                    )
                else:
                    self.db.update_tunnel(
                        tid, status=TunnelStatus.FAILED, pid=None,
                        last_error=error, stopped_at=time.time(),
                    )
                    self._notify_tunnel(tid, TunnelStatus.FAILED)
                del self._tunnels[tid]
                reaped.append(tid)
        return reaped

    # ── Scan operations ────────────────────────────────────────────────

    def start_scan(self, scan_id: int) -> bool:
        rec = self.db.get_scan(scan_id)
        if rec is None:
            return False

        try:
            target = ipaddress.ip_network(rec.target, strict=False)
        except ValueError as exc:
            self.db.update_scan(scan_id, status=ScanStatus.FAILED, error=str(exc))
            return False

        socks = None
        if rec.via_tunnel_id:
            tunnel = self.db.get_tunnel(rec.via_tunnel_id)
            if tunnel and tunnel.status == TunnelStatus.ACTIVE:
                spec = tunnel.spec
                socks = (spec.get("local_bind", "127.0.0.1"),
                         spec.get("local_port", 1080))

        plan = self.nmap.plan(target=target, profile=rec.profile, socks=socks)

        proc = SupervisedProcess(
            argv=plan.argv,
            env=plan.env,
            description=plan.description,
            log_lines=2000,
        )

        self.db.update_scan(scan_id, status=ScanStatus.RUNNING, started_at=time.time())
        self._notify_scan(scan_id, ScanStatus.RUNNING)

        try:
            proc.start()
        except OSError as exc:
            self.db.update_scan(
                scan_id, status=ScanStatus.FAILED, error=str(exc), finished_at=time.time()
            )
            return False

        self._scans[scan_id] = RunningScan(
            scan_id=scan_id, process=proc, cleanup_files=plan.cleanup_files,
        )
        return True

    def reap_scans(self) -> list[int]:
        """Check for finished scans, parse results."""
        reaped = []
        for sid, rs in list(self._scans.items()):
            outcome = rs.process.poll()
            if outcome is None:
                if time.monotonic() - rs.started_at > rs.timeout:
                    rs.process.stop(grace_seconds=5.0)
                    self.db.update_scan(
                        sid, status=ScanStatus.TIMED_OUT, finished_at=time.time()
                    )
                    self._cleanup_files(rs.cleanup_files)
                    del self._scans[sid]
                    reaped.append(sid)
                continue

            self._cleanup_files(rs.cleanup_files)

            if outcome.returncode == 0:
                xml = outcome.stdout_tail
                hosts, services = self._parse_nmap_xml(sid, xml)
                self.db.update_scan(
                    sid, status=ScanStatus.COMPLETED, finished_at=time.time(),
                    hosts_up=hosts, services_found=services, xml_output=xml,
                )
            else:
                error = self.nmap.interpret_exit(outcome.returncode, outcome.stderr_tail)
                self.db.update_scan(
                    sid, status=ScanStatus.FAILED, error=error, finished_at=time.time()
                )
            del self._scans[sid]
            reaped.append(sid)
            rec = self.db.get_scan(sid)
            self._notify_scan(sid, rec.status if rec else "unknown")
        return reaped

    def _parse_nmap_xml(self, scan_id: int, xml: str) -> tuple[int, int]:
        """Parse nmap XML output and store services. Returns (hosts_up, services_found)."""
        try:
            from defusedxml.ElementTree import fromstring
        except ImportError:
            from xml.etree.ElementTree import fromstring

        hosts_up = 0
        services_found = 0
        try:
            root = fromstring(xml)
        except Exception:
            return 0, 0

        for host_el in root.findall("host"):
            status = host_el.find("status")
            if status is not None and status.get("state") == "up":
                hosts_up += 1

            addr_el = host_el.find("address")
            host_ip = addr_el.get("addr", "") if addr_el is not None else ""

            hostname = ""
            hostnames_el = host_el.find("hostnames")
            if hostnames_el is not None:
                hn = hostnames_el.find("hostname")
                if hn is not None:
                    hostname = hn.get("name", "")

            ports_el = host_el.find("ports")
            if ports_el is None:
                continue

            for port_el in ports_el.findall("port"):
                state_el = port_el.find("state")
                if state_el is None or state_el.get("state") != "open":
                    continue

                svc_el = port_el.find("service")
                self.db.add_service(
                    scan_id,
                    host=host_ip,
                    hostname=hostname,
                    port=int(port_el.get("portid", 0)),
                    protocol=port_el.get("protocol", "tcp"),
                    state="open",
                    service_name=svc_el.get("name", "") if svc_el is not None else "",
                    product=svc_el.get("product", "") if svc_el is not None else "",
                    version=svc_el.get("version", "") if svc_el is not None else "",
                    extra_info=svc_el.get("extrainfo", "") if svc_el is not None else "",
                )
                services_found += 1

        return hosts_up, services_found

    # ── Reconcile loop ─────────────────────────────────────────────────

    def reconcile_once(self) -> None:
        """Single pass of the reconciler. Call in a loop or after each command."""
        self.reap_tunnels()
        self.reap_scans()

        for rec in self.db.list_tunnels(active_only=True):
            if rec.desired_state == DesiredState.DOWN and rec.id not in self._tunnels:
                self.stop_tunnel(rec.id)
            elif rec.desired_state == DesiredState.UP and rec.id not in self._tunnels:
                if rec.status not in (TunnelStatus.FAILED,):
                    self.start_tunnel(rec.id)

    def active_tunnel_count(self) -> int:
        return len(self._tunnels)

    def active_scan_count(self) -> int:
        return len(self._scans)

    # ── Internals ──────────────────────────────────────────────────────

    def _fail_tunnel(self, tunnel_id: int, error: str) -> None:
        self.db.update_tunnel(
            tunnel_id, status=TunnelStatus.FAILED, last_error=error, stopped_at=time.time()
        )
        self._notify_tunnel(tunnel_id, TunnelStatus.FAILED)

    def _notify_tunnel(self, tunnel_id: int, status: str) -> None:
        if self._on_tunnel_change:
            self._on_tunnel_change(tunnel_id, status)

    def _notify_scan(self, scan_id: int, status: str) -> None:
        if self._on_scan_change:
            self._on_scan_change(scan_id, status)

    @staticmethod
    def _cleanup_files(files: list[str]) -> None:
        for path in files:
            try:
                os.unlink(path)
            except OSError:
                pass

    def shutdown(self) -> None:
        """Stop all active processes."""
        for tid in list(self._tunnels):
            self.stop_tunnel(tid)
        for sid, rs in list(self._scans.items()):
            rs.process.stop(grace_seconds=5.0)
            self.db.update_scan(sid, status=ScanStatus.CANCELLED, finished_at=time.time())
            self._cleanup_files(rs.cleanup_files)
        self._scans.clear()
