"""Interactive mudale console — msfconsole-style REPL."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from mudale import __version__ as VERSION
from mudale_console.banner import render_banner
from mudale_console.completer import MudaleCompleter
from mudale_core.daemon import is_daemon_running, start_daemon
from mudale_core.modules import (
    Module,
    build_tunnel_spec,
    get_module,
    list_modules,
)
from mudale_core.state import StateDB
from mudale_core.supervisor import Engine
from mudale_engine.enums import (
    ScanStatus,
    TunnelKind,
    TunnelStatus,
)

STYLE = Style.from_dict({
    "prompt": "#00ff00 bold",
    "module": "#ffaf00 bold",
    "paren": "#888888",
})


def _paint(text: str, color: str) -> str:
    colors = {
        "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
        "cyan": "\033[36m", "grey": "\033[90m", "bold": "\033[1m",
        "dim": "\033[2m", "reset": "\033[0m",
    }
    if not sys.stdout.isatty():
        return text
    return f"{colors.get(color, '')}{text}{colors.get('reset', '')}"


def _status_color(status: str) -> str:
    if status in ("active", "completed", "ok", "running"):
        return "green"
    if status in ("starting", "stopping", "queued", "pending"):
        return "yellow"
    if status in ("failed", "error", "timed_out"):
        return "red"
    return "grey"


def _table(rows: list[dict], columns: list[tuple[str, str]], empty: str = "Nothing to show."):
    if not rows:
        print(_paint(empty, "grey"))
        return
    headers = [h for _, h in columns]
    widths = [len(h) for h in headers]
    cells = []
    for row in rows:
        line = [str(row.get(k, "") or "—") for k, _ in columns]
        cells.append(line)
        for i, v in enumerate(line):
            widths[i] = max(widths[i], len(v))
    print(_paint("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip(), "dim"))
    for line in cells:
        print("  ".join(v.ljust(widths[i]) for i, v in enumerate(line)).rstrip())


class MudaleConsole:
    """The interactive REPL."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".mudale"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db = StateDB(self.state_dir / "mudale.db")
        self.engine = Engine(db=self.db, state_dir=self.state_dir)
        self.current_module: Module | None = None
        self.current_workspace = self.db.ensure_default_workspace()

        history_file = self.state_dir / "history"
        self.session = PromptSession(
            completer=MudaleCompleter(self),
            history=FileHistory(str(history_file)),
            style=STYLE,
        )

    def get_prompt(self) -> HTML:
        if self.current_module:
            return HTML(
                f"<prompt>mudale</prompt> "
                f"<module>{self.current_module.type}</module>"
                f"<paren>(</paren><module>{self.current_module.name}</module><paren>)</paren> > "
            )
        return HTML("<prompt>mudale</prompt> > ")

    def run(self) -> int:
        print(render_banner(
            version=VERSION,
            module_count=len(list_modules()),
            tunnel_count=self.engine.active_tunnel_count(),
            scan_count=self.engine.active_scan_count(),
            engine_status="ready" if self.engine.ssh.is_available() else "no ssh",
        ))

        while True:
            try:
                text = self.session.prompt(self.get_prompt).strip()
            except KeyboardInterrupt:
                continue
            except EOFError:
                return self._cmd_exit([])

            if not text:
                continue

            self.db.add_history(text)
            parts = text.split()
            cmd = parts[0].lower()
            args = parts[1:]

            handler = {
                "use": self._cmd_use,
                "set": self._cmd_set,
                "unset": self._cmd_unset,
                "back": self._cmd_back,
                "run": self._cmd_run,
                "show": self._cmd_show,
                "jobs": self._cmd_jobs,
                "kill": self._cmd_kill,
                "sessions": self._cmd_sessions,
                "services": self._cmd_services,
                "forward": self._cmd_forward,
                "workspace": self._cmd_workspace,
                "sync": self._cmd_sync,
                "status": self._cmd_status,
                "history": self._cmd_history,
                "help": self._cmd_help,
                "banner": self._cmd_banner,
                "exit": self._cmd_exit,
                "quit": self._cmd_exit,
                "clear": self._cmd_clear,
            }.get(cmd)

            if handler is None:
                print(_paint(f"Unknown command: {cmd}. Type 'help' for available commands.", "red"))
                continue

            result = handler(args)
            if result is not None and result != 0:
                return result

    # ── Commands ───────────────────────────────────────────────────────

    def _cmd_use(self, args: list[str]) -> None:
        if not args:
            print(_paint("Usage: use <module>  (e.g. use tunnel/ssh_dynamic)", "yellow"))
            return
        mod = get_module(args[0])
        if mod is None:
            print(_paint(f"Unknown module: {args[0]}. Use 'show modules' to list.", "red"))
            return
        self.current_module = mod
        print(f"Using module {_paint(mod.full_name, 'cyan')}")

    def _cmd_set(self, args: list[str]) -> None:
        if self.current_module is None:
            print(_paint("No module selected. Use 'use <module>' first.", "yellow"))
            return
        if len(args) < 2:
            print(_paint("Usage: set <OPTION> <value>", "yellow"))
            return
        name, value = args[0], " ".join(args[1:])
        error = self.current_module.set_option(name, value)
        if error:
            print(_paint(error, "red"))
        else:
            print(f"{name.upper()} => {value}")

    def _cmd_unset(self, args: list[str]) -> None:
        if self.current_module is None:
            print(_paint("No module selected.", "yellow"))
            return
        if not args:
            print(_paint("Usage: unset <OPTION>", "yellow"))
            return
        error = self.current_module.unset_option(args[0])
        if error:
            print(_paint(error, "red"))
        else:
            print(f"Unset {args[0].upper()}")

    def _cmd_back(self, args: list[str]) -> None:
        self.current_module = None

    def _cmd_run(self, args: list[str]) -> None:
        if self.current_module is None:
            print(_paint("No module selected. Use 'use <module>' first.", "yellow"))
            return

        errors = self.current_module.validate()
        if errors:
            for e in errors:
                print(_paint(f"  [-] {e}", "red"))
            return

        mod = self.current_module
        if mod.type == "tunnel":
            self._run_tunnel(mod)
        elif mod.type == "scan":
            self._run_scan(mod)
        elif mod.type == "pivot":
            self._run_pivot(mod)
        else:
            print(_paint(f"Unknown module type: {mod.type}", "red"))

    def _run_tunnel(self, mod: Module) -> None:
        kind, spec = build_tunnel_spec(mod)
        print(f"[*] Creating {kind} tunnel...")

        rec = self.db.create_tunnel(
            workspace_id=self.current_workspace.id,
            kind=kind,
            spec=spec,
            label=mod.get_option("LABEL") or "",
        )

        success = self.engine.start_tunnel(rec.id)
        if success:
            from mudale_engine.adapters.ssh import SshAdapter
            from mudale_engine.specs import parse_spec as ps
            parsed = ps(kind, spec)
            desc = SshAdapter.describe(parsed)
            print(f"[{_paint('+', 'green')}] Tunnel {rec.id} active — {desc}")
        else:
            updated = self.db.get_tunnel(rec.id)
            error = updated.last_error if updated else "Unknown error"
            print(f"[{_paint('-', 'red')}] Tunnel failed: {error}")

    def _run_scan(self, mod: Module) -> None:
        target = mod.get_option("TARGET")
        profile = mod.get_option("PROFILE") or "standard"
        via = mod.get_option("VIA_TUNNEL")

        print(f"[*] Starting {profile} scan of {target}...")

        rec = self.db.create_scan(
            workspace_id=self.current_workspace.id,
            target=target,
            profile=profile,
            via_tunnel_id=int(via) if via else None,
        )

        success = self.engine.start_scan(rec.id)
        if not success:
            updated = self.db.get_scan(rec.id)
            print(f"[{_paint('-', 'red')}] Scan failed: {updated.error if updated else 'Unknown'}")
            return

        print(f"[*] Scan {rec.id} running... (waiting for results)")

        while rec.id in self.engine._scans:
            self.engine.reap_scans()
            time.sleep(1.0)
            sys.stdout.write(".")
            sys.stdout.flush()

        print()
        updated = self.db.get_scan(rec.id)
        if updated and updated.status == ScanStatus.COMPLETED:
            print(
                f"[{_paint('+', 'green')}] Scan complete: "
                f"{updated.hosts_up} hosts up, {updated.services_found} services found"
            )
            services = self.db.list_services(scan_id=rec.id)
            if services:
                print()
                _table(
                    [{"host": s.host, "port": s.port, "proto": s.protocol,
                      "service": s.service_name, "product": s.product, "version": s.version}
                     for s in services],
                    [("host", "HOST"), ("port", "PORT"), ("proto", "PROTO"),
                     ("service", "SERVICE"), ("product", "PRODUCT"), ("version", "VERSION")],
                )
        else:
            print(f"[{_paint('-', 'red')}] Scan failed: {updated.error if updated else 'Unknown'}")

    def _run_pivot(self, mod: Module) -> None:
        tunnel_id = int(mod.get_option("TUNNEL_ID"))
        target = mod.get_option("TARGET")
        profile = mod.get_option("PROFILE") or "quick"

        tunnel = self.db.get_tunnel(tunnel_id)
        if tunnel is None or tunnel.status != TunnelStatus.ACTIVE:
            print(_paint(f"Tunnel {tunnel_id} is not active. Start a SOCKS tunnel first.", "red"))
            return

        print(f"[*] Phase 1: Scanning {target} through tunnel {tunnel_id}...")
        rec = self.db.create_scan(
            self.current_workspace.id, target, profile, via_tunnel_id=tunnel_id,
        )
        success = self.engine.start_scan(rec.id)
        if not success:
            updated = self.db.get_scan(rec.id)
            print(f"[{_paint('-', 'red')}] Scan failed: {updated.error if updated else 'Unknown'}")
            return

        while rec.id in self.engine._scans:
            self.engine.reap_scans()
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(1.0)
        print()

        updated = self.db.get_scan(rec.id)
        if not updated or updated.status != ScanStatus.COMPLETED:
            print(f"[{_paint('-', 'red')}] Scan failed: {updated.error if updated else 'Unknown'}")
            return

        services = self.db.list_services(scan_id=rec.id)
        if not services:
            print(_paint("[*] No open services found.", "yellow"))
            return

        print(
            f"[{_paint('+', 'green')}] Found {len(services)} services."
            " Creating local forwards...\n"
        )

        base_port = 10000
        ssh_spec = tunnel.spec.get("endpoint", {})
        created = 0

        for svc in services:
            if svc.port in (22,):
                continue

            local_port = base_port + created
            fwd_spec = {
                "endpoint": ssh_spec,
                "local_bind": "127.0.0.1",
                "local_port": local_port,
                "target_host": svc.host,
                "target_port": svc.port,
            }

            fwd_rec = self.db.create_tunnel(
                self.current_workspace.id,
                TunnelKind.SSH_LOCAL,
                fwd_spec,
                label=f"{svc.service_name}@{svc.host}:{svc.port}",
            )
            ok = self.engine.start_tunnel(fwd_rec.id)
            status_str = _paint("active", "green") if ok else _paint("failed", "red")
            print(
                f"  127.0.0.1:{local_port} → {svc.host}:{svc.port}"
                f"/{svc.protocol} ({svc.service_name})  [{status_str}]"
            )
            if ok:
                created += 1

        print(f"\n[{_paint('+', 'green')}] {created} tunnels created. Use 'jobs' to see all.")

    def _cmd_show(self, args: list[str]) -> None:
        sub = args[0].lower() if args else "options"
        if sub == "options":
            if self.current_module is None:
                print(_paint("No module selected.", "yellow"))
                return
            print(f"\nModule options ({_paint(self.current_module.full_name, 'cyan')}):\n")
            _table(
                self.current_module.get_options_table(),
                [
                    ("name", "Name"), ("current", "Current"),
                    ("required", "Required"), ("description", "Description"),
                ],
            )
            print()
        elif sub == "modules":
            print(f"\n{'Modules':^60}\n{'=' * 60}\n")
            for m in list_modules():
                print(f"  {_paint(m['name'], 'cyan'):40s} {m['description']}")
            print()
        elif sub == "tunnels":
            self._cmd_jobs([])
        elif sub == "scans":
            scans = self.db.list_scans(self.current_workspace.id)
            _table(
                [{"id": s.id, "target": s.target, "profile": s.profile,
                  "status": _paint(s.status, _status_color(s.status)),
                  "hosts": s.hosts_up, "services": s.services_found}
                 for s in scans],
                [("id", "ID"), ("target", "TARGET"), ("profile", "PROFILE"),
                 ("status", "STATUS"), ("hosts", "HOSTS"), ("services", "SERVICES")],
                empty="No scans in this workspace.",
            )
        elif sub == "services":
            self._cmd_services([])
        else:
            print(_paint(
                f"Unknown: show {sub}. Try: options, modules, tunnels, scans, services",
                "yellow",
            ))

    def _cmd_jobs(self, args: list[str]) -> None:
        self.engine.reap_tunnels()
        tunnels = self.db.list_tunnels(self.current_workspace.id)
        if not tunnels:
            print(_paint("No tunnels in this workspace.", "grey"))
            return

        from mudale_engine.adapters.ssh import SshAdapter
        from mudale_engine.specs import SpecError, parse_spec

        rows = []
        for t in tunnels:
            try:
                spec = parse_spec(t.kind, t.spec)
                desc = SshAdapter.describe(spec)
            except (SpecError, TypeError):
                desc = t.kind
            rows.append({
                "id": t.id,
                "type": t.kind,
                "status": _paint(t.status, _status_color(t.status)),
                "description": desc,
            })

        _table(rows, [
            ("id", "ID"), ("type", "TYPE"),
            ("status", "STATUS"), ("description", "DESCRIPTION"),
        ])

    def _cmd_kill(self, args: list[str]) -> None:
        if not args:
            print(_paint("Usage: kill <tunnel_id>", "yellow"))
            return
        try:
            tid = int(args[0])
        except ValueError:
            print(_paint("Tunnel ID must be a number.", "red"))
            return
        success = self.engine.stop_tunnel(tid)
        if success:
            print(f"[{_paint('*', 'yellow')}] Tunnel {tid} stopped")
        else:
            print(f"[{_paint('-', 'red')}] Failed to stop tunnel {tid}")

    def _cmd_sessions(self, args: list[str]) -> None:
        tunnels = self.db.list_tunnels(active_only=True)
        active = [t for t in tunnels if t.status == TunnelStatus.ACTIVE]
        if not active:
            print(_paint("No active sessions.", "grey"))
            return
        print(f"\nActive sessions: {len(active)}\n")
        self._cmd_jobs([])

    def _cmd_services(self, args: list[str]) -> None:
        services = self.db.list_services(workspace_id=self.current_workspace.id)
        if not services:
            print(_paint("No services discovered yet. Run a scan first.", "grey"))
            return
        _table(
            [{"host": s.host, "port": s.port, "proto": s.protocol,
              "service": s.service_name, "product": s.product,
              "version": s.version}
             for s in services],
            [("host", "HOST"), ("port", "PORT"), ("proto", "PROTO"),
             ("service", "SERVICE"), ("product", "PRODUCT"), ("version", "VERSION")],
        )

    def _cmd_forward(self, args: list[str]) -> None:
        """Quick local forward: forward <host> <port> [local_port] [tunnel_id]"""
        if len(args) < 2:
            print(_paint("Usage: forward <host> <port> [local_port] [via_tunnel_id]", "yellow"))
            print(_paint("  Creates a local forward to a discovered service.", "grey"))
            return

        host = args[0]
        try:
            target_port = int(args[1])
        except ValueError:
            print(_paint("Port must be a number.", "red"))
            return

        local_port = int(args[2]) if len(args) > 2 else 10000 + target_port

        active_tunnels = [t for t in self.db.list_tunnels(active_only=True)
                          if t.status == TunnelStatus.ACTIVE and t.kind == TunnelKind.SSH_DYNAMIC]

        if len(args) > 3:
            tunnel_id = int(args[3])
            tunnel = self.db.get_tunnel(tunnel_id)
        elif active_tunnels:
            tunnel = active_tunnels[0]
        else:
            print(_paint(
                "No active SOCKS tunnel. Create one first (use tunnel/ssh_dynamic).", "red",
            ))
            return

        if tunnel is None or tunnel.status != TunnelStatus.ACTIVE:
            print(_paint(f"Tunnel {tunnel.id if tunnel else '?'} is not active.", "red"))
            return

        ssh_spec = tunnel.spec.get("endpoint", {})
        fwd_spec = {
            "endpoint": ssh_spec,
            "local_bind": "127.0.0.1",
            "local_port": local_port,
            "target_host": host,
            "target_port": target_port,
        }

        rec = self.db.create_tunnel(
            self.current_workspace.id,
            TunnelKind.SSH_LOCAL,
            fwd_spec,
            label=f"{host}:{target_port}",
        )
        ok = self.engine.start_tunnel(rec.id)
        if ok:
            print(
                f"[{_paint('+', 'green')}] "
                f"127.0.0.1:{local_port} → {host}:{target_port} (tunnel {rec.id})"
            )
        else:
            updated = self.db.get_tunnel(rec.id)
            print(f"[{_paint('-', 'red')}] Failed: {updated.last_error if updated else 'Unknown'}")

    def _cmd_workspace(self, args: list[str]) -> None:
        if not args:
            ws = self.current_workspace
            print(f"Current workspace: {_paint(ws.name, 'cyan')} (id={ws.id})")
            return
        sub = args[0].lower()
        if sub == "list":
            workspaces = self.db.list_workspaces()
            for ws in workspaces:
                marker = " *" if ws.id == self.current_workspace.id else ""
                print(
                    f"  {ws.id}  {_paint(ws.name, 'cyan')}"
                    f"{_paint(marker, 'green')}  {ws.description}"
                )
        elif sub == "use" and len(args) > 1:
            ws = self.db.get_workspace(args[1])
            if ws is None:
                print(_paint(f"Workspace '{args[1]}' not found.", "red"))
            else:
                self.current_workspace = ws
                print(f"Switched to workspace: {_paint(ws.name, 'cyan')}")
        elif sub == "add" and len(args) > 1:
            name = args[1]
            ws = self.db.create_workspace(name)
            self.current_workspace = ws
            print(f"Created and switched to workspace: {_paint(ws.name, 'cyan')}")
        elif sub == "show":
            ws = self.current_workspace
            print(f"  Name:   {ws.name}")
            print(f"  ID:     {ws.id}")
            print(f"  CIDRs:  {', '.join(ws.cidrs) if ws.cidrs else 'none'}")
        else:
            print(_paint("Usage: workspace [list|use <name>|add <name>|show]", "yellow"))

    def _cmd_sync(self, args: list[str]) -> None:
        """Sync CLI state to the web dashboard (requires Django)."""
        if not args:
            print(_paint("Usage: sync <engagement_id>", "yellow"))
            print(_paint("  Pushes tunnels/scans/services to the dashboard database.", "grey"))
            return

        try:
            engagement_id = int(args[0])
        except ValueError:
            print(_paint("Engagement ID must be a number.", "red"))
            return

        try:
            from mudale_core.sync import SyncBridge
        except ImportError:
            print(_paint("Sync bridge not available.", "red"))
            return

        try:
            bridge = SyncBridge(
                self.db,
                engagement_id=engagement_id,
                workspace_id=self.current_workspace.id,
            )
            report = bridge.sync()
        except Exception as exc:
            print(f"[{_paint('-', 'red')}] Sync failed: {exc}")
            print(_paint("  Is the dashboard database running? (mudale server)", "grey"))
            return

        print(f"[{_paint('+', 'green')}] Sync complete:")
        print(f"  Tunnels pushed:  {report.tunnels_pushed}")
        print(f"  Tunnels updated: {report.tunnels_updated}")
        print(f"  Scans pushed:    {report.scans_pushed}")
        print(f"  Scans updated:   {report.scans_updated}")
        print(f"  Services pushed: {report.services_pushed}")
        print(f"  Commands pulled: {report.tunnels_pulled}")
        if report.errors:
            print(f"\n  {_paint('Errors:', 'yellow')}")
            for err in report.errors:
                print(f"    {_paint('!', 'yellow')} {err}")

    def _cmd_status(self, args: list[str]) -> None:
        caps = self.engine.capabilities
        print("\n  Engine capabilities:")
        for cap, available in caps.items():
            marker = _paint("✓", "green") if available else _paint("✗", "red")
            print(f"    {marker}  {cap}")

        daemon_pid = is_daemon_running(self.state_dir)
        if daemon_pid:
            print(f"\n  Background daemon: {_paint(f'running (PID {daemon_pid})', 'green')}")
        else:
            print(f"\n  Background daemon: {_paint('not running', 'grey')}")

        tunnels = self.db.list_tunnels(active_only=True)
        active = [t for t in tunnels if t.status == TunnelStatus.ACTIVE]
        print(f"  Active tunnels:    {len(active)}")
        print(f"  Workspace:         {self.current_workspace.name}")
        print()

    def _cmd_history(self, args: list[str]) -> None:
        history = self.db.get_history(limit=20)
        if not history:
            print(_paint("No command history.", "grey"))
            return
        for i, cmd in enumerate(history, 1):
            print(f"  {_paint(str(i), 'dim'):>6}  {cmd}")

    def _cmd_help(self, args: list[str]) -> None:
        print(f"""
{_paint('Core Commands', 'bold')}
{'=' * 40}
  {_paint('use', 'cyan')} <module>       Select a module (tunnel/scan/pivot)
  {_paint('back', 'cyan')}               Deselect the current module
  {_paint('set', 'cyan')} <opt> <val>    Set a module option
  {_paint('unset', 'cyan')} <opt>        Clear a module option
  {_paint('show', 'cyan')} options       Show current module options
  {_paint('show', 'cyan')} modules       List all available modules
  {_paint('run', 'cyan')}                Execute the current module

{_paint('Session Management', 'bold')}
{'=' * 40}
  {_paint('jobs', 'cyan')}               List active tunnels and scans
  {_paint('kill', 'cyan')} <id>          Stop a tunnel or scan
  {_paint('sessions', 'cyan')}           List active SSH sessions
  {_paint('services', 'cyan')}           List discovered services
  {_paint('forward', 'cyan')} <h> <p>    Quick local forward to a service

{_paint('Workspace', 'bold')}
{'=' * 40}
  {_paint('workspace', 'cyan')}          Show current workspace
  {_paint('workspace', 'cyan')} list     List workspaces
  {_paint('workspace', 'cyan')} use <n>  Switch workspace
  {_paint('workspace', 'cyan')} add <n>  Create workspace

{_paint('Dashboard', 'bold')}
{'=' * 40}
  {_paint('sync', 'cyan')} <eng_id>     Push state to web dashboard

{_paint('Info', 'bold')}
{'=' * 40}
  {_paint('status', 'cyan')}             Engine + tunnel overview
  {_paint('history', 'cyan')}            Command history
  {_paint('banner', 'cyan')}             Show banner
  {_paint('clear', 'cyan')}              Clear screen
  {_paint('exit', 'cyan')}               Quit (tunnels keep running in background)
""")

    def _cmd_banner(self, args: list[str]) -> None:
        print(render_banner(
            version=VERSION,
            module_count=len(list_modules()),
            tunnel_count=self.engine.active_tunnel_count(),
            scan_count=self.engine.active_scan_count(),
            engine_status="ready" if self.engine.ssh.is_available() else "no ssh",
        ))

    def _cmd_exit(self, args: list[str]) -> int:
        active = self.engine.active_tunnel_count()
        if active > 0:
            print(f"\n[*] {active} active tunnel(s) will continue in the background.")
            print("[*] Starting background daemon...")
            pid = start_daemon(self.state_dir)
            print(
                f"[{_paint('+', 'green')}] Daemon running (PID {pid})."
                " Use 'mudale' to reconnect.\n"
            )
        else:
            print()
        return 0

    def _cmd_clear(self, args: list[str]) -> None:
        print("\033[2J\033[H", end="")
