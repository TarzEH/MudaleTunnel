"""
TunnelManager - Shared backend logic for managing SSH tunnels.
Used by both CLI and web interface.
"""
import subprocess
import platform
import socket
import threading
import uuid
import time
import signal
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from collections import deque


class TunnelManager:
    """Manages SSH tunnels with thread-safe operations."""
    
    def __init__(self):
        self.active_tunnels: Dict[str, Dict] = {}
        self.tunnel_logs: Dict[str, deque] = {}  # Store logs for each tunnel
        self.tunnel_metrics: Dict[str, Dict] = {}  # Store metrics for each tunnel
        self.lock = threading.Lock()
        self.myip = self._get_local_ip()
    
    def _get_local_ip(self) -> str:
        """Get local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 53))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def _generate_tunnel_id(self) -> str:
        """Generate unique tunnel ID."""
        return str(uuid.uuid4())
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is already in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return False
            except OSError:
                return True
    
    def _find_free_port(self, start_port: int = 8000) -> int:
        """Find a free port starting from start_port."""
        port = start_port
        while self._is_port_in_use(port):
            port += 1
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
                self.tunnel_logs[tunnel_id] = deque(maxlen=1000)
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
    
    def create_static_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        target_host: str,
        remote_port: int,
        local_port: Optional[int] = None,
        execute: bool = True
    ) -> Tuple[str, str]:
        """
        Create a static SSH tunnel (port forwarding).
        
        Returns:
            Tuple of (tunnel_id, ssh_command)
        """
        if local_port is None:
            local_port = remote_port
        
        # Check if local port is in use
        if self._is_port_in_use(local_port):
            raise ValueError(f"Local port {local_port} is already in use")
        
        tunnel_id = self._generate_tunnel_id()
        ssh_command = f"ssh -L {local_port}:{target_host}:{remote_port} {ssh_user}@{ssh_host} -N -f"
        
        if execute:
            try:
                process = self._execute_ssh_command(ssh_command, tunnel_id)
                
                with self.lock:
                    self.active_tunnels[tunnel_id] = {
                        "id": tunnel_id,
                        "type": "static",
                        "pid": process.pid,
                        "process": process,
                        "command": ssh_command,
                        "local_port": local_port,
                        "remote_host": target_host,
                        "remote_port": remote_port,
                        "ssh_user": ssh_user,
                        "ssh_host": ssh_host,
                        "status": "active",
                        "created_at": datetime.now().isoformat()
                    }
                    self._log_tunnel_event(tunnel_id, f"Static tunnel created: {local_port} -> {target_host}:{remote_port}")
                    self._update_metrics(tunnel_id, status="active")
                
                return tunnel_id, ssh_command
            except Exception as e:
                self._log_tunnel_event(tunnel_id, f"Failed to create tunnel: {str(e)}", "ERROR")
                raise
        else:
            return tunnel_id, ssh_command
    
    def create_dynamic_tunnel(
        self,
        ssh_user: str,
        ssh_host: str,
        local_port: Optional[int] = None,
        execute: bool = True
    ) -> Tuple[str, str]:
        """
        Create a dynamic SSH tunnel (SOCKS proxy).
        
        Returns:
            Tuple of (tunnel_id, ssh_command)
        """
        if local_port is None:
            # Try common SOCKS ports
            for port in [1080, 8080, 9050]:
                if not self._is_port_in_use(port):
                    local_port = port
                    break
            if local_port is None:
                local_port = self._find_free_port(1080)
        
        # Check if local port is in use
        if self._is_port_in_use(local_port):
            raise ValueError(f"Local port {local_port} is already in use")
        
        tunnel_id = self._generate_tunnel_id()
        ssh_command = f"ssh -D {local_port} {ssh_user}@{ssh_host} -N -f"
        
        if execute:
            try:
                process = self._execute_ssh_command(ssh_command, tunnel_id)
                
                with self.lock:
                    self.active_tunnels[tunnel_id] = {
                        "id": tunnel_id,
                        "type": "dynamic",
                        "pid": process.pid,
                        "process": process,
                        "command": ssh_command,
                        "local_port": local_port,
                        "ssh_user": ssh_user,
                        "ssh_host": ssh_host,
                        "status": "active",
                        "created_at": datetime.now().isoformat()
                    }
                    self._log_tunnel_event(tunnel_id, f"Dynamic tunnel created: SOCKS proxy on port {local_port}")
                    self._update_metrics(tunnel_id, status="active")
                
                return tunnel_id, ssh_command
            except Exception as e:
                self._log_tunnel_event(tunnel_id, f"Failed to create tunnel: {str(e)}", "ERROR")
                raise
        else:
            return tunnel_id, ssh_command
    
    def _execute_ssh_command(self, command: str, tunnel_id: str) -> subprocess.Popen:
        """Execute SSH command in background."""
        is_windows = platform.system() == "Windows"
        
        if is_windows:
            # Windows: Use CREATE_NEW_PROCESS_GROUP
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creation_flags
            )
        else:
            # Unix/Linux/macOS
            process = subprocess.Popen(
                command.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
        
        # Wait a moment to check if process started successfully
        time.sleep(0.5)
        if process.poll() is not None:
            # Process already terminated (likely failed)
            stderr = process.stderr.read().decode() if process.stderr else "Unknown error"
            raise RuntimeError(f"SSH command failed: {stderr}")
        
        return process
    
    def list_tunnels(self) -> List[Dict]:
        """List all tunnels (active and inactive)."""
        with self.lock:
            tunnels = []
            for tunnel_id, tunnel_info in self.active_tunnels.items():
                # Check if process is still running
                process = tunnel_info.get("process")
                if process:
                    if process.poll() is not None:
                        tunnel_info["status"] = "stopped"
                    else:
                        tunnel_info["status"] = "active"
                        self._update_metrics(tunnel_id)
                
                tunnel_copy = tunnel_info.copy()
                tunnel_copy.pop("process", None)  # Remove process object for serialization
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
                    
                    # Wait for process to terminate
                    try:
                        process.wait(timeout=5)
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
        count = 0
        tunnel_ids = list(self.active_tunnels.keys())
        for tunnel_id in tunnel_ids:
            if self.stop_tunnel(tunnel_id):
                count += 1
        return count
    
    def get_tunnel_logs(self, tunnel_id: str, limit: int = 100) -> List[str]:
        """Get logs for a tunnel."""
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
                # Update uptime
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
            
            # Check process
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
            
            # Check port
            if local_port:
                if self._is_port_in_use(local_port):
                    health["port_listening"] = True
                else:
                    health["reason"] = f"Port {local_port} not listening"
                    return health
            
            health["healthy"] = True
            self._update_metrics(tunnel_id, last_status_check=datetime.now().isoformat())
            return health
