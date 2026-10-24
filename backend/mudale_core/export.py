"""Export stored scan results to structured formats (JSON / CSV).

Pure functions over ``StateDB`` so the CLI, the interactive console and (later)
the REST API can share one implementation and one output schema.

JSON schema (``schema_version`` 1)::

    {
      "schema_version": 1,
      "scan": {id, workspace_id, target, profile, status, via_tunnel_id,
               hosts_up, services_found, error, queued_at, started_at,
               finished_at},          # timestamps: ISO 8601 UTC or null
      "hosts": [
        {"host": "10.0.0.5", "hostname": "",
         "ports": [{port, protocol, state, service, product, version,
                    extra_info}]}
      ]
    }

CSV: one row per host/port, with the header ``CSV_COLUMNS``.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

from mudale_core.state import StateDB

SCHEMA_VERSION = 1
SUPPORTED_FORMATS = ("json", "csv")

CSV_COLUMNS = (
    "scan_id", "host", "hostname", "port", "protocol", "state",
    "service", "product", "version", "extra_info",
)


class ExportError(ValueError):
    """Unknown scan or unsupported format."""


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def build_scan_export(db: StateDB, scan_id: int) -> dict:
    """Return the scan metadata plus its services grouped by host."""
    scan = db.get_scan(scan_id)
    if scan is None:
        raise ExportError(f"Scan {scan_id} not found")

    hosts: dict[str, dict] = {}
    for svc in db.list_services(scan_id=scan_id):
        entry = hosts.setdefault(
            svc.host, {"host": svc.host, "hostname": svc.hostname, "ports": []}
        )
        if svc.hostname and not entry["hostname"]:
            entry["hostname"] = svc.hostname
        entry["ports"].append({
            "port": svc.port,
            "protocol": svc.protocol,
            "state": svc.state,
            "service": svc.service_name,
            "product": svc.product,
            "version": svc.version,
            "extra_info": svc.extra_info,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "scan": {
            "id": scan.id,
            "workspace_id": scan.workspace_id,
            "target": scan.target,
            "profile": scan.profile,
            "status": str(scan.status),
            "via_tunnel_id": scan.via_tunnel_id,
            "hosts_up": scan.hosts_up,
            "services_found": scan.services_found,
            "error": scan.error,
            "queued_at": _iso(scan.queued_at),
            "started_at": _iso(scan.started_at),
            "finished_at": _iso(scan.finished_at),
        },
        "hosts": list(hosts.values()),
    }


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def render_csv(data: dict) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    scan_id = data["scan"]["id"]
    for host in data["hosts"]:
        for p in host["ports"]:
            writer.writerow([
                scan_id, host["host"], host["hostname"], p["port"], p["protocol"],
                p["state"], p["service"], p["product"], p["version"], p["extra_info"],
            ])
    return buf.getvalue()


def export_scan(db: StateDB, scan_id: int, fmt: str = "json") -> str:
    """Render a stored scan as ``fmt`` ("json" or "csv"). Raises ExportError."""
    fmt = fmt.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ExportError(
            f"Unsupported format '{fmt}' (choose from: {', '.join(SUPPORTED_FORMATS)})"
        )
    data = build_scan_export(db, scan_id)
    return render_json(data) if fmt == "json" else render_csv(data)
