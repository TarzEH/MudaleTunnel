"""
FastAPI web application for MudaleTunnel web interface.
"""
import asyncio
import subprocess
import platform
import os
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel
import json

from tunnel_manager import TunnelManager
import config

app = FastAPI(title="MudaleTunnel Web Interface")

# Mount static files and templates
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 template environment
if os.path.exists("templates"):
    jinja_env = Environment(loader=FileSystemLoader("templates"))
else:
    jinja_env = None

# Shared tunnel manager instance (can be set from main.py)
tunnel_manager = TunnelManager()

# WebSocket connections for real-time updates (using set for O(1) operations)
active_connections: set = set()

# Scan tasks storage
scan_tasks: Dict[str, Dict] = {}


class ScanRequest(BaseModel):
    target: str
    scan_type: str = "full"  # quick, full, service, stealth, udp


class StaticTunnelRequest(BaseModel):
    ssh_user: str
    ssh_host: str
    target_host: str
    remote_port: int
    local_port: Optional[int] = None
    execute: bool = True


class DynamicTunnelRequest(BaseModel):
    ssh_user: str
    ssh_host: str
    local_port: Optional[int] = None
    execute: bool = True


class RemoteTunnelRequest(BaseModel):
    ssh_user: str
    ssh_host: str
    remote_bind_port: int
    target_host: str
    target_port: int
    bind_address: str = "127.0.0.1"
    execute: bool = True


class RemoteDynamicTunnelRequest(BaseModel):
    ssh_user: str
    ssh_host: str
    remote_socks_port: int
    bind_address: str = "127.0.0.1"
    execute: bool = True


class ProxychainsConfig(BaseModel):
    proxy_type: str = "socks5"  # socks4, socks5, http
    proxy_host: str
    proxy_port: int
    chain_type: str = "strict_chain"  # strict_chain, dynamic_chain, random_chain


async def broadcast_tunnel_update(message: dict):
    """Broadcast tunnel update to all connected WebSocket clients. Optimized with set."""
    disconnected = set()
    for connection in active_connections.copy():  # Copy to avoid modification during iteration
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)
    
    # Remove disconnected connections (O(1) with set)
    active_connections.difference_update(disconnected)


def get_nmap_command(target: str, scan_type: str) -> list:
    """Get nmap command based on scan type."""
    base_cmd = ["nmap"]
    
    scan_types = {
        "quick": ["-F", "-T4"],  # Fast scan, top 100 ports
        "full": ["-p-", "-sV"],  # All ports, service detection
        "service": ["-sV", "-sC"],  # Service detection + scripts
        "stealth": ["-sS", "-T2"],  # SYN scan, slower
        "udp": ["-sU", "-T4"],  # UDP scan
        "intense": ["-T4", "-A", "-v"],  # Intense scan with OS detection
    }
    
    if scan_type in scan_types:
        base_cmd.extend(scan_types[scan_type])
    else:
        # Default to full scan
        base_cmd.extend(["-p-", "-sV"])
    
    base_cmd.append(target)
    return base_cmd


def run_nmap_scan(target: str, scan_id: str, scan_type: str = "full"):
    """Run nmap scan in background with specified scan type."""
    try:
        scan_tasks[scan_id]["status"] = "running"
        scan_tasks[scan_id]["progress"] = f"Starting {scan_type} scan..."
        scan_tasks[scan_id]["scan_type"] = scan_type
        
        nmap_cmd = get_nmap_command(target, scan_type)
        result = subprocess.run(
            nmap_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=config.NMAP_SCAN_TIMEOUT
        )
        
        scan_tasks[scan_id]["status"] = "completed"
        scan_tasks[scan_id]["output"] = result.stdout
        scan_tasks[scan_id]["progress"] = "Scan completed"
        
        # Parse services from nmap output
        services = []
        in_port_section = False
        
        for line in result.stdout.splitlines():
            line = line.strip()
            
            # Skip header lines and empty lines
            if not line or "PORT" in line and "STATE" in line and "SERVICE" in line:
                in_port_section = True
                continue
            
            # Match nmap port output formats:
            # "22/tcp   open  ssh"
            # "80/tcp   open  http    Apache httpd 2.4.41"
            # "443/tcp  open  https"
            # "22/tcp   open     ssh"
            if ("/tcp" in line or "/udp" in line) and "open" in line:
                parts = line.split()
                if len(parts) >= 3:
                    # Find the index of "open"
                    open_idx = next((i for i, p in enumerate(parts) if p == "open"), None)
                    if open_idx is not None and open_idx > 0:
                        port = parts[0]  # e.g., "22/tcp"
                        state = parts[open_idx]  # "open"
                        # Service name is usually after "open"
                        service = parts[open_idx + 1] if open_idx + 1 < len(parts) else "unknown"
                        
                        # Skip if service is "filtered", "closed", etc.
                        if service not in ["filtered", "closed", "unfiltered"]:
                            services.append({
                                "port": port,
                                "state": state,
                                "service": service
                            })
        
        scan_tasks[scan_id]["services"] = services
        scan_tasks[scan_id]["service_count"] = len(services)
        
        # Log for debugging if no services found
        if len(services) == 0:
            # Check if there are any "open" lines at all
            open_lines = [l for l in result.stdout.splitlines() if "open" in l.lower()]
            scan_tasks[scan_id]["parse_debug"] = {
                "output_lines": len(result.stdout.splitlines()),
                "open_lines_found": len(open_lines),
                "sample_open_lines": open_lines[:5] if open_lines else [],
                "sample_output": result.stdout[:1000] if result.stdout else "No output",
                "stderr": result.stderr[:500] if result.stderr else "No stderr"
            }
        
    except subprocess.TimeoutExpired:
        scan_tasks[scan_id]["status"] = "failed"
        scan_tasks[scan_id]["error"] = "Scan timed out"
    except Exception as e:
        scan_tasks[scan_id]["status"] = "failed"
        scan_tasks[scan_id]["error"] = str(e)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main dashboard."""
    if jinja_env is None:
        return HTMLResponse(content="<h1>Templates directory not found</h1>", status_code=500)
    template = jinja_env.get_template("index.html")
    html_content = template.render(request=request)
    return HTMLResponse(content=html_content)


@app.post("/api/scan")
async def initiate_scan(scan_request: ScanRequest, background_tasks: BackgroundTasks):
    """Initiate an nmap scan."""
    import uuid
    scan_id = str(uuid.uuid4())
    
    scan_tasks[scan_id] = {
        "id": scan_id,
        "target": scan_request.target,
        "status": "queued",
        "progress": "Queued for execution",
        "created_at": datetime.now().isoformat()
    }
    
    background_tasks.add_task(run_nmap_scan, scan_request.target, scan_id, scan_request.scan_type)
    
    return {"scan_id": scan_id, "status": "queued"}


@app.get("/api/scan/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """Get scan status and results."""
    if scan_id not in scan_tasks:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    task = scan_tasks[scan_id].copy()
    # Remove large output if scan is still running (to reduce payload)
    if task.get("status") == "running":
        task.pop("output", None)
        task.pop("parse_debug", None)
    
    # Always include services (even if empty list)
    # This ensures the frontend always gets a services array
    if "services" not in task:
        task["services"] = []
    
    # Include parse_debug if available (for troubleshooting)
    if task.get("status") == "completed" and "parse_debug" in task:
        # Keep parse_debug for completed scans with no services
        pass
    
    return task


@app.get("/api/scans")
async def get_all_scans():
    """Get all scan history."""
    scans = []
    for scan_id, task in scan_tasks.items():
        scan_info = {
            "id": scan_id,
            "target": task.get("target", "unknown"),
            "status": task.get("status", "unknown"),
            "scan_type": task.get("scan_type", "full"),
            "created_at": task.get("created_at"),
            "progress": task.get("progress", ""),
            "service_count": len(task.get("services", []))
        }
        scans.append(scan_info)
    # Sort by created_at descending (newest first)
    scans.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"scans": scans}


@app.get("/api/services")
async def get_services():
    """Get all discovered services from completed scans."""
    all_services = []
    for scan_id, task in scan_tasks.items():
        if task.get("status") == "completed" and "services" in task:
            for service in task["services"]:
                service["scan_id"] = scan_id
                service["target"] = task.get("target", "unknown")
                service["scan_type"] = task.get("scan_type", "full")
                all_services.append(service)
    return {"services": all_services}


@app.post("/api/tunnels/static")
async def create_static_tunnel(tunnel_request: StaticTunnelRequest):
    """Create a static SSH tunnel."""
    try:
        tunnel_id, ssh_command = tunnel_manager.create_static_tunnel(
            tunnel_request.ssh_user,
            tunnel_request.ssh_host,
            tunnel_request.target_host,
            tunnel_request.remote_port,
            tunnel_request.local_port,
            tunnel_request.execute
        )
        
        # Broadcast update
        await broadcast_tunnel_update({
            "type": "tunnel_created",
            "tunnel_id": tunnel_id,
            "tunnel_type": "static"
        })
        
        tunnel_info = tunnel_manager.get_tunnel(tunnel_id)
        return {
            "success": True,
            "tunnel_id": tunnel_id,
            "command": ssh_command,
            "tunnel": tunnel_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tunnel: {str(e)}")


@app.post("/api/tunnels/dynamic")
async def create_dynamic_tunnel(tunnel_request: DynamicTunnelRequest):
    """Create a dynamic SSH tunnel (SOCKS proxy)."""
    try:
        tunnel_id, ssh_command = tunnel_manager.create_dynamic_tunnel(
            tunnel_request.ssh_user,
            tunnel_request.ssh_host,
            tunnel_request.local_port,
            tunnel_request.execute
        )
        
        # Broadcast update
        await broadcast_tunnel_update({
            "type": "tunnel_created",
            "tunnel_id": tunnel_id,
            "tunnel_type": "dynamic"
        })
        
        tunnel_info = tunnel_manager.get_tunnel(tunnel_id)
        return {
            "success": True,
            "tunnel_id": tunnel_id,
            "command": ssh_command,
            "tunnel": tunnel_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tunnel: {str(e)}")


@app.post("/api/tunnels/remote")
async def create_remote_tunnel(tunnel_request: RemoteTunnelRequest):
    """Create a remote SSH tunnel (reverse port forwarding).
    
    Use case: When you can SSH out but can't bind ports on the compromised host.
    The listening port is bound on the SSH server (attacker machine).
    """
    try:
        tunnel_id, ssh_command = tunnel_manager.create_remote_tunnel(
            tunnel_request.ssh_user,
            tunnel_request.ssh_host,
            tunnel_request.remote_bind_port,
            tunnel_request.target_host,
            tunnel_request.target_port,
            tunnel_request.bind_address,
            tunnel_request.execute
        )
        
        # Broadcast update
        await broadcast_tunnel_update({
            "type": "tunnel_created",
            "tunnel_id": tunnel_id,
            "tunnel_type": "remote"
        })
        
        tunnel_info = tunnel_manager.get_tunnel(tunnel_id)
        return {
            "success": True,
            "tunnel_id": tunnel_id,
            "command": ssh_command,
            "tunnel": tunnel_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tunnel: {str(e)}")


@app.post("/api/tunnels/remote-dynamic")
async def create_remote_dynamic_tunnel(tunnel_request: RemoteDynamicTunnelRequest):
    """Create a remote dynamic SSH tunnel (reverse SOCKS proxy).
    
    Use case: When you can SSH out but need flexible access to multiple internal services.
    The SOCKS proxy port is bound on the SSH server (attacker machine).
    Requires OpenSSH 7.6+ client.
    """
    try:
        tunnel_id, ssh_command = tunnel_manager.create_remote_dynamic_tunnel(
            tunnel_request.ssh_user,
            tunnel_request.ssh_host,
            tunnel_request.remote_socks_port,
            tunnel_request.bind_address,
            tunnel_request.execute
        )
        
        # Broadcast update
        await broadcast_tunnel_update({
            "type": "tunnel_created",
            "tunnel_id": tunnel_id,
            "tunnel_type": "remote_dynamic"
        })
        
        tunnel_info = tunnel_manager.get_tunnel(tunnel_id)
        return {
            "success": True,
            "tunnel_id": tunnel_id,
            "command": ssh_command,
            "tunnel": tunnel_info
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create tunnel: {str(e)}")


@app.get("/api/tunnels")
async def list_tunnels():
    """List all tunnels."""
    tunnels = tunnel_manager.list_tunnels()
    return {"tunnels": tunnels}


@app.get("/api/tunnels/{tunnel_id}")
async def get_tunnel(tunnel_id: str):
    """Get tunnel details."""
    tunnel = tunnel_manager.get_tunnel(tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return tunnel


@app.delete("/api/tunnels/{tunnel_id}")
async def stop_tunnel(tunnel_id: str):
    """Stop a specific tunnel."""
    success = tunnel_manager.stop_tunnel(tunnel_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    
    # Broadcast update
    await broadcast_tunnel_update({
        "type": "tunnel_stopped",
        "tunnel_id": tunnel_id
    })
    
    return {"success": True, "message": "Tunnel stopped"}


@app.delete("/api/tunnels")
async def stop_all_tunnels():
    """Stop all tunnels."""
    count = tunnel_manager.stop_all_tunnels()
    
    # Broadcast update
    await broadcast_tunnel_update({
        "type": "all_tunnels_stopped",
        "count": count
    })
    
    return {"success": True, "count": count}


@app.get("/api/tunnels/{tunnel_id}/logs")
async def get_tunnel_logs(tunnel_id: str, limit: Optional[int] = None):
    """Get tunnel logs."""
    if limit is None:
        limit = config.DEFAULT_LOG_LIMIT
    """Get tunnel logs."""
    logs = tunnel_manager.get_tunnel_logs(tunnel_id, limit)
    return {"tunnel_id": tunnel_id, "logs": logs}


@app.get("/api/tunnels/{tunnel_id}/metrics")
async def get_tunnel_metrics(tunnel_id: str):
    """Get tunnel metrics."""
    metrics = tunnel_manager.get_tunnel_metrics(tunnel_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return metrics


@app.get("/api/tunnels/{tunnel_id}/health")
async def check_tunnel_health(tunnel_id: str):
    """Check tunnel health."""
    health = tunnel_manager.check_tunnel_health(tunnel_id)
    return health


@app.websocket("/ws/tunnels")
async def websocket_tunnels(websocket: WebSocket):
    """WebSocket endpoint for real-time tunnel updates."""
    await websocket.accept()
    active_connections.add(websocket)  # O(1) addition with set
    
    try:
        # Send initial tunnel list
        tunnels = tunnel_manager.list_tunnels()
        await websocket.send_json({
            "type": "initial_state",
            "tunnels": tunnels
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for any message (ping/pong for keepalive)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=config.WEBSOCKET_TIMEOUT)
                # Echo back or handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text("ping")
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)  # O(1) removal with set


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.DEFAULT_WEB_HOST, port=config.DEFAULT_WEB_PORT)
