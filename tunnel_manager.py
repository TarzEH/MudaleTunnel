"""
TunnelManager - Shared backend logic for managing SSH tunnels.
Used by both CLI and web interface.
"""
import subprocess
import platform
import re
import socket
import threading
import uuid
import time
import signal
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque

import config


# Pattern for validating SSH input fields (user, host, address)
_SAFE_INPUT_PATTERN = re.compile(r'^[a-zA-Z0-9._@\-:/]+$')


class TunnelManager:
    """Manages SSH tunnels with thread-safe operations."""

    def __init__(self):
        self.active_tunnels: Dict[str, Dict] = {}
        self.tunnel_logs: Dict[str, deque] = {}
        self.tunnel_metrics: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.myip = self._get_local_ip()
        self._port_cache: Dict[int, Tuple[bool, float]] = {}

    # ── Validation ──────────────────────────────────────────────

    @staticmethod
    def _validate_input(value: str, field_name: str) -> str:
        """Validate SSH input to prevent command injection.

        Rejects values containing shell metacharacters (;, |, &, $, backticks, etc).
        """
        if not value or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")
        value = value.strip()
        if not _SAFE_INPUT_PATTERN.match(value):
            raise ValueError(
                f"Invalid {field_name}: '{value}' contains disallowed characters. "
                f"Only alphanumeric, dots, hyphens, underscores, @, colons, and slashes are allowed."
            )
        return value

    # ── Internal helpers ────────────────────────────────────────

    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((config.NMAP_DNS_SERVER, config.NMAP_DNS_PORT))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _generate_tunnel_id(self) -> str:
        """Generate unique tunnel ID."""
        return str(uuid.uuid4())

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use. Uses caching for performance."""
        current_time = time.time()

        if port in self._port_cache:
            is_available, cache_time = self._port_cache[port]
            if current_time - cache_time < config.PORT_CHECK_CACHE_TTL:
                return not is_available

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(config.PORT_CHECK_TIMEOUT)
                s.bind(('127.0.0.1', port))
                is_available = True
            except (OSError, socket.timeout):
                is_available = False

        self._port_cache[port] = (is_available, current_time)
        return not is_available

    def _find_free_port(self, start_port: Optional[int] = None) -> int:
        """Find a free port starting from start_port."""
        if start_port is None:
            start_port = config.DEFAULT_FREE_PORT_START
        port = start_port
        max_attempts = config.MAX_PORT_SEARCH_ATTEMPTS
        attempts = 0
        while self._is_port_in_use(port) and attempts < max_attempts:
            port += 1
            attempts += 1
        if attempts >= max_attempts:
            raise RuntimeError(f"Could not find free port starting from {start_port}")
        return port

    def _parse_port(self, port_str: str) -> int:
        """Parse port string (e.g., '22/tcp' -> 22)."""
        if '/' in port_str:
            return int(port_str.split('/')[0])
        return int(port_str)

    def _log_tunnel_event(self, tunnel_id: str, message: str, level: str = "INFO"):
        """Log an event for a tunnel."""
        with self.lock:
            if tunnel_id not in self.tunnel_logs:
                self.tunnel_logs[tunnel_id] = deque(maxlen=config.MAX_LOG_ENTRIES_PER_TUNNEL)
            timestamp = datetime.now().isoformat()
            log_entry = f"[{timestamp}] [{level}] {message}"
            self.tunnel_logs[tunnel_id].append(log_entry)

    def _update_metrics(self, tunnel_id: str, **kwargs):
        """Update tunnel metrics."""
        with self.lock:
            if tunnel_id not in self.tunnel_metrics:
                self.tunnel_metrics[tunnel_id] = {
                    "created_at": datetime.now().isoformat(),
                    "uptime_seconds": 0,
                    "status_checks": 0,
                    "last_status_check": None
                }
            self.tunnel_metrics[tunnel_id].update(kwargs)
            if "created_at" in self.tunnel_metrics[tunnel_id]:
                created = datetime.fromisoformat(self.tunnel_metrics[tunnel_id]["created_at"])
                uptime = (datetime.now() - created).total_seconds()
                self.tunnel_metrics[tunnel_id]["uptime_seconds"] = uptime

    # ── Tunnel execution core ───────────────────────────────────

    def _execute_ssh_command(self, cmd_list: List[str], tunnel_id: str) -> subprocess.Popen:
        """Execute SSH command in background using a safe argument list."""
        is_windows = platform.system() == "Windows"

        if is_windows:
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags
            )
        else:
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )

        time.sleep(config.SSH_STARTUP_DELAY)
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else "Unknown error"
            raise RuntimeError(f"SSH command failed: {stderr}")

        return process

    def _register_and_execute_tunnel(
        self,
        tunnel_id: str,
        tunnel_type: str,
        cmd_list: List[str],
        log_message: str,
        metadata: Dict,
        execute: bool,
    ) -> Tuple[str, str]:
        """Shared tunnel creation logic — validates, executes, registers, and logs.

        Returns:
            Tuple of (tunnel_id, ssh_command_display_string)
        """
        display_command = " ".join(cmd_list)

        if not execute:
            return tunnel_id, display_command

        try:
            process = self._execute_ssh_command(cmd_list, tunnel_id)

            with self.lock:
                self.active_tunnels[tunnel_id] = {
                    "id": tunnel_id,
                    "type": tunnel_type,
                    "pid": process.pid,
                    "process": process,
                    "command": display_command,
                    "ssh_user": metadata.get("ssh_user"),
                    "ssh_host": metadata.get("ssh_host"),
                    "status": "active",
                    "created_at": datetime.now().isoformat(),
                    **{k: v for k, v in metadata.items() if k not in ("ssh_user", "ssh_host")},
                }
                self._log_tunnel_event(tunnel_id, log_message)
                self._update_metrics(tunnel_id, status="active")

            return tunnel_id, display_command
        except Exception as e:
            self._log_tunnel_event(tunnel_id, f"Failed to create tunnel: {str(e)}", "ERROR")
            raise

    # ── Public tunnel creation API ──────────────────────────────

    def create_static_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        target_host: str,
        remote_port: int,
        local_port: Optional[int] = None,
        execute: bool = True
    ) -> Tuple[str, str]:
        """Create a static SSH tunnel (local port forwarding)."""
        ssh_user = self._validate_input(ssh_user, "SSH user")
        ssh_host = self._validate_input(ssh_host, "SSH host")
        target_host = self._validate_input(target_host, "target host")

        if local_port is None:
            local_port = remote_port
        if self._is_port_in_use(local_port):
            raise ValueError(f"Local port {local_port} is already in use")

        tunnel_id = self._generate_tunnel_id()
        cmd_list = ["ssh", "-L", f"{local_port}:{target_host}:{remote_port}",
                     f"{ssh_user}@{ssh_host}", "-N", "-f"]

        return self._register_and_execute_tunnel(
            tunnel_id=tunnel_id,
            tunnel_type="static",
            cmd_list=cmd_list,
            log_message=f"Static tunnel created: {local_port} -> {target_host}:{remote_port}",
            metadata={
                "local_port": local_port,
                "remote_host": target_host,
                "remote_port": remote_port,
                "ssh_user": ssh_user,
                "ssh_host": ssh_host,
            },
            execute=execute,
        )

    def create_dynamic_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        local_port: Optional[int] = None,
        execute: bool = True
    ) -> Tuple[str, str]:
        """Create a dynamic SSH tunnel (SOCKS proxy)."""
        ssh_user = self._validate_input(ssh_user, "SSH user")
        ssh_host = self._validate_input(ssh_host, "SSH host")

        if local_port is None:
            for port in config.DEFAULT_SOCKS_PORTS:
                if not self._is_port_in_use(port):
                    local_port = port
                    break
            if local_port is None:
                local_port = self._find_free_port(config.SOCKS_PORT_START)

        if self._is_port_in_use(local_port):
            raise ValueError(f"Local port {local_port} is already in use")

        tunnel_id = self._generate_tunnel_id()
        cmd_list = ["ssh", "-D", str(local_port),
                     f"{ssh_user}@{ssh_host}", "-N", "-f"]

        return self._register_and_execute_tunnel(
            tunnel_id=tunnel_id,
            tunnel_type="dynamic",
            cmd_list=cmd_list,
            log_message=f"Dynamic tunnel created: SOCKS proxy on port {local_port}",
            metadata={
                "local_port": local_port,
                "ssh_user": ssh_user,
                "ssh_host": ssh_host,
            },
            execute=execute,
        )

    def create_remote_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        remote_bind_port: int,
        target_host: str,
        target_port: int,
        bind_address: str = "127.0.0.1",
        execute: bool = True
    ) -> Tuple[str, str]:
        """Create a remote SSH tunnel (reverse port forwarding)."""
        ssh_user = self._validate_input(ssh_user, "SSH user")
        ssh_host = self._validate_input(ssh_host, "SSH host")
        target_host = self._validate_input(target_host, "target host")
        bind_address = self._validate_input(bind_address, "bind address")

        tunnel_id = self._generate_tunnel_id()
        cmd_list = ["ssh", "-R",
                     f"{bind_address}:{remote_bind_port}:{target_host}:{target_port}",
                     f"{ssh_user}@{ssh_host}", "-N", "-f"]

        return self._register_and_execute_tunnel(
            tunnel_id=tunnel_id,
            tunnel_type="remote",
            cmd_list=cmd_list,
            log_message=f"Remote tunnel created: {bind_address}:{remote_bind_port} -> {target_host}:{target_port}",
            metadata={
                "remote_bind_port": remote_bind_port,
                "target_host": target_host,
                "target_port": target_port,
                "bind_address": bind_address,
                "ssh_user": ssh_user,
                "ssh_host": ssh_host,
            },
            execute=execute,
        )

    def create_remote_dynamic_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        remote_socks_port: int,
        bind_address: str = "127.0.0.1",
        execute: bool = True
    ) -> Tuple[str, str]:
        """Create a remote dynamic SSH tunnel (reverse SOCKS proxy). Requires OpenSSH 7.6+."""
        ssh_user = self._validate_input(ssh_user, "SSH user")
        ssh_host = self._validate_input(ssh_host, "SSH host")
        bind_address = self._validate_input(bind_address, "bind address")

        tunnel_id = self._generate_tunnel_id()
        cmd_list = ["ssh", "-R", f"{bind_address}:{remote_socks_port}",
                     f"{ssh_user}@{ssh_host}", "-N", "-f"]

        return self._register_and_execute_tunnel(
            tunnel_id=tunnel_id,
            tunnel_type="remote_dynamic",
            cmd_list=cmd_list,
            log_message=f"Remote dynamic tunnel created: SOCKS proxy on {bind_address}:{remote_socks_port}",
            metadata={
                "remote_socks_port": remote_socks_port,
                "bind_address": bind_address,
                "ssh_user": ssh_user,
                "ssh_host": ssh_host,
            },
            execute=execute,
        )

    # ── Tunnel management ───────────────────────────────────────

    def list_tunnels(self) -> List[Dict]:
        """List all tunnels (active and inactive)."""
        with self.lock:
            tunnel_items = list(self.active_tunnels.items())

        tunnels = []
        for tunnel_id, tunnel_info in tunnel_items:
            process = tunnel_info.get("process")
            if process:
                if process.poll() is not None:
                    tunnel_info["status"] = "stopped"
                else:
                    tunnel_info["status"] = "active"
                    with self.lock:
                        self._update_metrics(tunnel_id)

            tunnel_copy = tunnel_info.copy()
            tunnel_copy.pop("process", None)
            tunnels.append(tunnel_copy)

        return tunnels

    def get_tunnel(self, tunnel_id: str) -> Optional[Dict]:
        """Get tunnel details by ID."""
        with self.lock:
            if tunnel_id in self.active_tunnels:
                tunnel = self.active_tunnels[tunnel_id].copy()
                tunnel.pop("process", None)
                return tunnel
            return None

    def stop_tunnel(self, tunnel_id: str) -> bool:
        """Stop a specific tunnel."""
        with self.lock:
            if tunnel_id not in self.active_tunnels:
                return False

            tunnel = self.active_tunnels[tunnel_id]
            process = tunnel.get("process")

            if process:
                try:
                    is_windows = platform.system() == "Windows"
                    if is_windows:
                        process.terminate()
                    else:
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)

                    try:
                        process.wait(timeout=config.SSH_PROCESS_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        process.kill()

                    self._log_tunnel_event(tunnel_id, "Tunnel stopped")
                    tunnel["status"] = "stopped"
                    return True
                except Exception as e:
                    self._log_tunnel_event(tunnel_id, f"Error stopping tunnel: {str(e)}", "ERROR")
                    return False
            else:
                tunnel["status"] = "stopped"
                return True

    def stop_all_tunnels(self) -> int:
        """Stop all active tunnels."""
        with self.lock:
            tunnel_ids = list(self.active_tunnels.keys())

        count = 0
        for tunnel_id in tunnel_ids:
            if self.stop_tunnel(tunnel_id):
                count += 1
        return count

    def get_tunnel_logs(self, tunnel_id: str, limit: Optional[int] = None) -> List[str]:
        """Get logs for a tunnel."""
        if limit is None:
            limit = config.DEFAULT_LOG_LIMIT
        with self.lock:
            if tunnel_id in self.tunnel_logs:
                logs = list(self.tunnel_logs[tunnel_id])
                return logs[-limit:] if limit else logs
            return []

    def get_tunnel_metrics(self, tunnel_id: str) -> Optional[Dict]:
        """Get metrics for a tunnel."""
        with self.lock:
            if tunnel_id in self.tunnel_metrics:
                metrics = self.tunnel_metrics[tunnel_id].copy()
                if "created_at" in metrics:
                    created = datetime.fromisoformat(metrics["created_at"])
                    uptime = (datetime.now() - created).total_seconds()
                    metrics["uptime_seconds"] = uptime
                return metrics
            return None

    def check_tunnel_health(self, tunnel_id: str) -> Dict:
        """Check if tunnel is healthy (port listening, process running)."""
        with self.lock:
            if tunnel_id not in self.active_tunnels:
                return {"healthy": False, "reason": "Tunnel not found"}

            tunnel = self.active_tunnels[tunnel_id]
            process = tunnel.get("process")
            local_port = tunnel.get("local_port")

            health = {
                "healthy": False,
                "process_running": False,
                "port_listening": False,
                "reason": ""
            }

            if process:
                if process.poll() is None:
                    health["process_running"] = True
                else:
                    health["reason"] = "Process terminated"
                    tunnel["status"] = "stopped"
                    return health
            else:
                health["reason"] = "Process not found"
                return health

            if local_port:
                if self._is_port_in_use(local_port):
                    health["port_listening"] = True
                else:
                    health["reason"] = f"Port {local_port} not listening"
                    return health

            health["healthy"] = True
            self._update_metrics(tunnel_id, last_status_check=datetime.now().isoformat())
            return health
