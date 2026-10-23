"""SQLite state manager — standalone tunnel/scan/service persistence.

Replaces Django ORM for standalone mode. All state lives in a single SQLite
file at ~/.mudale/mudale.db by default.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from mudale_engine.enums import (
    DesiredState,
    ScanStatus,
    TunnelStatus,
)

DEFAULT_DB_PATH = Path.home() / ".mudale" / "mudale.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    cidrs       TEXT NOT NULL DEFAULT '[]',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tunnels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  INTEGER NOT NULL REFERENCES workspaces(id),
    kind          TEXT NOT NULL,
    label         TEXT NOT NULL DEFAULT '',
    spec          TEXT NOT NULL,
    desired_state TEXT NOT NULL DEFAULT 'up',
    status        TEXT NOT NULL DEFAULT 'pending',
    pid           INTEGER,
    last_error    TEXT NOT NULL DEFAULT '',
    restart_count INTEGER NOT NULL DEFAULT 0,
    started_at    REAL,
    stopped_at    REAL,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id  INTEGER NOT NULL REFERENCES workspaces(id),
    target        TEXT NOT NULL,
    profile       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    via_tunnel_id INTEGER REFERENCES tunnels(id),
    hosts_up      INTEGER NOT NULL DEFAULT 0,
    services_found INTEGER NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    xml_output    TEXT NOT NULL DEFAULT '',
    queued_at     REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL
);

CREATE TABLE IF NOT EXISTS services (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id      INTEGER NOT NULL REFERENCES scans(id),
    host         TEXT NOT NULL,
    hostname     TEXT NOT NULL DEFAULT '',
    port         INTEGER NOT NULL,
    protocol     TEXT NOT NULL DEFAULT 'tcp',
    state        TEXT NOT NULL DEFAULT 'open',
    service_name TEXT NOT NULL DEFAULT '',
    product      TEXT NOT NULL DEFAULT '',
    version      TEXT NOT NULL DEFAULT '',
    extra_info   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS command_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    command    TEXT NOT NULL,
    timestamp  REAL NOT NULL
);
"""


@dataclass
class Workspace:
    id: int
    name: str
    description: str = ""
    cidrs: list[str] = field(default_factory=list)
    created_at: float = 0.0


@dataclass
class TunnelRecord:
    id: int
    workspace_id: int
    kind: str
    label: str
    spec: dict
    desired_state: str = DesiredState.UP
    status: str = TunnelStatus.PENDING
    pid: int | None = None
    last_error: str = ""
    restart_count: int = 0
    started_at: float | None = None
    stopped_at: float | None = None
    created_at: float = 0.0


@dataclass
class ScanRecord:
    id: int
    workspace_id: int
    target: str
    profile: str
    status: str = ScanStatus.QUEUED
    via_tunnel_id: int | None = None
    hosts_up: int = 0
    services_found: int = 0
    error: str = ""
    xml_output: str = ""
    queued_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class ServiceRecord:
    id: int
    scan_id: int
    host: str
    hostname: str = ""
    port: int = 0
    protocol: str = "tcp"
    state: str = "open"
    service_name: str = ""
    product: str = ""
    version: str = ""
    extra_info: str = ""


class StateDB:
    """Thread-safe SQLite state manager."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Workspaces ─────────────────────────────────────────────────────

    def create_workspace(
        self, name: str, description: str = "", cidrs: list[str] | None = None,
    ) -> Workspace:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO workspaces (name, description, cidrs, created_at) VALUES (?, ?, ?, ?)",
                (name, description, json.dumps(cidrs or []), now),
            )
            return Workspace(
                id=cur.lastrowid, name=name, description=description,
                cidrs=cidrs or [], created_at=now,
            )

    def get_workspace(self, name: str) -> Workspace | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return self._row_to_workspace(row)

    def get_workspace_by_id(self, ws_id: int) -> Workspace | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_workspace(row)

    def list_workspaces(self) -> list[Workspace]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM workspaces ORDER BY id").fetchall()
            return [self._row_to_workspace(r) for r in rows]

    def ensure_default_workspace(self) -> Workspace:
        ws = self.get_workspace("default")
        if ws is None:
            ws = self.create_workspace("default", description="Default workspace")
        return ws

    @staticmethod
    def _row_to_workspace(row) -> Workspace:
        return Workspace(
            id=row["id"], name=row["name"], description=row["description"],
            cidrs=json.loads(row["cidrs"]), created_at=row["created_at"],
        )

    # ── Tunnels ────────────────────────────────────────────────────────

    def create_tunnel(
        self, workspace_id: int, kind: str, spec: dict, label: str = "",
    ) -> TunnelRecord:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO tunnels "
                "(workspace_id, kind, label, spec, desired_state, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    workspace_id, kind, label, json.dumps(spec),
                    DesiredState.UP, TunnelStatus.PENDING, now,
                ),
            )
            return TunnelRecord(
                id=cur.lastrowid, workspace_id=workspace_id, kind=kind,
                label=label, spec=spec, created_at=now,
            )

    def get_tunnel(self, tunnel_id: int) -> TunnelRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tunnels WHERE id = ?", (tunnel_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_tunnel(row)

    def list_tunnels(
        self, workspace_id: int | None = None, active_only: bool = False,
    ) -> list[TunnelRecord]:
        with self._conn() as conn:
            query = "SELECT * FROM tunnels"
            params: list = []
            conditions = []
            if workspace_id is not None:
                conditions.append("workspace_id = ?")
                params.append(workspace_id)
            if active_only:
                conditions.append("desired_state = ?")
                params.append(DesiredState.UP)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY id"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_tunnel(r) for r in rows]

    def update_tunnel(self, tunnel_id: int, **kwargs) -> None:
        if "spec" in kwargs and isinstance(kwargs["spec"], dict):
            kwargs["spec"] = json.dumps(kwargs["spec"])
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [tunnel_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE tunnels SET {sets} WHERE id = ?", vals)

    @staticmethod
    def _row_to_tunnel(row) -> TunnelRecord:
        return TunnelRecord(
            id=row["id"], workspace_id=row["workspace_id"], kind=row["kind"],
            label=row["label"], spec=json.loads(row["spec"]),
            desired_state=row["desired_state"], status=row["status"],
            pid=row["pid"], last_error=row["last_error"],
            restart_count=row["restart_count"],
            started_at=row["started_at"], stopped_at=row["stopped_at"],
            created_at=row["created_at"],
        )

    # ── Scans ──────────────────────────────────────────────────────────

    def create_scan(
        self, workspace_id: int, target: str, profile: str, via_tunnel_id: int | None = None
    ) -> ScanRecord:
        now = time.time()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO scans (workspace_id, target, profile, via_tunnel_id, queued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (workspace_id, target, profile, via_tunnel_id, now),
            )
            return ScanRecord(
                id=cur.lastrowid, workspace_id=workspace_id, target=target,
                profile=profile, via_tunnel_id=via_tunnel_id, queued_at=now,
            )

    def get_scan(self, scan_id: int) -> ScanRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
            if row is None:
                return None
            return self._row_to_scan(row)

    def list_scans(self, workspace_id: int | None = None) -> list[ScanRecord]:
        with self._conn() as conn:
            if workspace_id is not None:
                rows = conn.execute(
                    "SELECT * FROM scans WHERE workspace_id = ? ORDER BY id DESC", (workspace_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM scans ORDER BY id DESC").fetchall()
            return [self._row_to_scan(r) for r in rows]

    def update_scan(self, scan_id: int, **kwargs) -> None:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [scan_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE scans SET {sets} WHERE id = ?", vals)

    @staticmethod
    def _row_to_scan(row) -> ScanRecord:
        return ScanRecord(
            id=row["id"], workspace_id=row["workspace_id"], target=row["target"],
            profile=row["profile"], status=row["status"],
            via_tunnel_id=row["via_tunnel_id"], hosts_up=row["hosts_up"],
            services_found=row["services_found"], error=row["error"],
            xml_output=row["xml_output"], queued_at=row["queued_at"],
            started_at=row["started_at"], finished_at=row["finished_at"],
        )

    # ── Services ───────────────────────────────────────────────────────

    def add_service(self, scan_id: int, **kwargs) -> int:
        cols = ["scan_id"] + list(kwargs.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [scan_id] + list(kwargs.values())
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO services ({', '.join(cols)}) VALUES ({placeholders})", vals
            )
            return cur.lastrowid

    def list_services(
        self, scan_id: int | None = None, workspace_id: int | None = None,
    ) -> list[ServiceRecord]:
        with self._conn() as conn:
            if scan_id is not None:
                rows = conn.execute(
                    "SELECT * FROM services WHERE scan_id = ? ORDER BY host, port", (scan_id,)
                ).fetchall()
            elif workspace_id is not None:
                rows = conn.execute(
                    "SELECT s.* FROM services s JOIN scans sc ON s.scan_id = sc.id "
                    "WHERE sc.workspace_id = ? ORDER BY s.host, s.port",
                    (workspace_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM services ORDER BY host, port").fetchall()
            return [self._row_to_service(r) for r in rows]

    @staticmethod
    def _row_to_service(row) -> ServiceRecord:
        return ServiceRecord(
            id=row["id"], scan_id=row["scan_id"], host=row["host"],
            hostname=row["hostname"], port=row["port"], protocol=row["protocol"],
            state=row["state"], service_name=row["service_name"],
            product=row["product"], version=row["version"],
            extra_info=row["extra_info"],
        )

    # ── History ────────────────────────────────────────────────────────

    def add_history(self, command: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO command_history (command, timestamp) VALUES (?, ?)",
                (command, time.time()),
            )

    def get_history(self, limit: int = 100) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT command FROM command_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [r["command"] for r in reversed(rows)]
