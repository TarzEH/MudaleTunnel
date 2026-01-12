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

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# Scan tasks storage
scan_tasks: Dict[str, Dict] = {}


class ScanRequest(BaseModel):
    target: str


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


async def broadcast_tunnel_update(message: dict):
    """Broadcast tunnel update to all connected WebSocket clients."""
    disconnected = []
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.append(connection)
    
    # Remove disconnected connections
    for conn in disconnected:
        if conn in active_connections:
            active_connections.remove(conn)


def run_nmap_scan(target: str, scan_id: str):
    """Run nmap scan in background."""
    try:
        scan_tasks[scan_id]["status"] = "running"
        scan_tasks[scan_id]["progress"] = "Starting scan..."
        
        result = subprocess.run(
            ["nmap", "-p-", "-sV", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300
        )
        
        scan_tasks[scan_id]["status"] = "completed"
        scan_tasks[scan_id]["output"] = result.stdout
        scan_tasks[scan_id]["progress"] = "Scan completed"
        
        # Parse services
        services = []
        for line in result.stdout.splitlines():
            if "open" in line:
                parts = line.split()
                if len(parts) >= 3:
                    port, state, service = parts[0], parts[1], parts[2]
                    services.append({
                        "port": port,
                        "state": state,
                        "service": service
                    })
        scan_tasks[scan_id]["services"] = services
        
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
    
    background_tasks.add_task(run_nmap_scan, scan_request.target, scan_id)
    
    return {"scan_id": scan_id, "status": "queued"}


@app.get("/api/scan/status/{scan_id}")
async def get_scan_status(scan_id: str):
    """Get scan status and results."""
    if scan_id not in scan_tasks:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    task = scan_tasks[scan_id].copy()
    # Remove output if scan is still running (to reduce payload)
    if task.get("status") == "running":
        task.pop("output", None)
        task.pop("services", None)
    
    return task


@app.get("/api/services")
async def get_services():
    """Get all discovered services from completed scans."""
    all_services = []
    for scan_id, task in scan_tasks.items():
        if task.get("status") == "completed" and "services" in task:
            for service in task["services"]:
                service["scan_id"] = scan_id
                service["target"] = task.get("target", "unknown")
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
async def get_tunnel_logs(tunnel_id: str, limit: int = 100):
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
    active_connections.append(websocket)
    
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
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back or handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text("ping")
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
