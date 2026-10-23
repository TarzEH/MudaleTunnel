"""Entry point — interactive console, one-shot commands, server mode, or remote client.

    mudale                          Interactive console (default)
    mudale console                  Same as above
    mudale server                   Start web dashboard (Django + React)
    mudale tunnel create ...        One-shot tunnel creation
    mudale scan run ...             One-shot scan
    mudale jobs                     List active tunnels
    mudale services                 List discovered services
    mudale remote login ...         Connect to a remote server (original CLI)
    mudale remote tunnels           List tunnels on remote server
    mudale daemon start|stop|status Manage background daemon
"""

from __future__ import annotations

import argparse
import sys
import time

from mudale_cli import output
from mudale_cli.client import ApiError, Client, Config

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DENIED = 2
EXIT_UNREACHABLE = 3

POLL_INTERVAL = 2.0


# ── Interactive Console ────────────────────────────────────────────────


def cmd_console(args) -> int:
    from mudale_console.app import MudaleConsole

    console = MudaleConsole()
    return console.run()


# ── Server Mode ────────────────────────────────────────────────────────


def cmd_server(args) -> int:
    """Start the web dashboard (Django + React)."""
    try:
        import django  # noqa: F401
    except ImportError:
        output.error(
            "Django is not installed. Install server extras:\n"
            "  pip install mudaletunnel[server]\n"
            "  # or: uv pip install 'mudaletunnel[server]'"
        )
        return EXIT_ERROR

    import os
    import subprocess

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mudale.settings.dev")

    port = getattr(args, "port", 8000)
    bind = getattr(args, "bind", "127.0.0.1")
    print(f"Starting MudaleTunnel dashboard on {bind}:{port}...")
    print("Press Ctrl+C to stop.\n")

    try:
        subprocess.run(  # noqa: S603
            [sys.executable, "manage.py", "runserver", f"{bind}:{port}"],
            check=True,
        )
    except KeyboardInterrupt:
        print("\nServer stopped.")
    return EXIT_OK


# ── Daemon Management ──────────────────────────────────────────────────


def cmd_daemon(args) -> int:
    from mudale_core.daemon import is_daemon_running, start_daemon, stop_daemon

    sub = getattr(args, "daemon_action", "status")
    if sub == "start":
        pid = start_daemon()
        if pid:
            output.success(f"Daemon running (PID {pid})")
        return EXIT_OK
    elif sub == "stop":
        stop_daemon()
        output.success("Daemon stopped")
        return EXIT_OK
    else:
        pid = is_daemon_running()
        if pid:
            print(f"Daemon running (PID {pid})")
        else:
            print("Daemon not running")
        return EXIT_OK


# ── One-shot Tunnel Commands ───────────────────────────────────────────


def cmd_oneshot_tunnel_create(args) -> int:
    from mudale_core.supervisor import Engine

    engine = Engine()
    ws = engine.db.ensure_default_workspace()
    if hasattr(args, "workspace") and args.workspace:
        ws = engine.db.get_workspace(args.workspace) or ws

    endpoint = {"user": args.username, "host": args.rhost, "port": args.rport or 22}
    if args.identity:
        endpoint["identity_file"] = args.identity
    endpoint["strict_host_key_checking"] = not args.insecure

    kind = args.type
    if kind == "ligolo":
        spec = {
            "agent_addr": args.rhost,
            "listen_port": args.lport or 11601,
            "tun_name": getattr(args, "tun_name", None) or "ligolo",
            "laddr": args.lhost or "0.0.0.0",  # noqa: S104
            "selfcert": not getattr(args, "no_selfcert", False),
        }
    elif kind == "ssh_local":
        spec = {
            "endpoint": endpoint,
            "local_bind": args.lhost or "127.0.0.1",
            "local_port": args.lport,
            "target_host": args.target_host,
            "target_port": args.target_port,
        }
    elif kind == "ssh_dynamic":
        spec = {
            "endpoint": endpoint,
            "local_bind": args.lhost or "127.0.0.1",
            "local_port": args.lport or 1080,
        }
    elif kind == "ssh_remote":
        spec = {
            "endpoint": endpoint,
            "remote_bind": args.remote_bind or "127.0.0.1",
            "remote_port": args.remote_port,
            "target_host": args.target_host,
            "target_port": args.target_port,
        }
    elif kind == "ssh_remote_dynamic":
        spec = {
            "endpoint": endpoint,
            "remote_bind": args.remote_bind or "127.0.0.1",
            "remote_port": args.remote_port,
        }
    else:
        output.error(f"Unknown tunnel type: {kind}")
        return EXIT_ERROR

    rec = engine.db.create_tunnel(ws.id, kind, spec, label=args.label or "")
    success = engine.start_tunnel(rec.id)

    if success:
        from mudale_engine.specs import parse_spec
        parsed = parse_spec(kind, spec)
        if kind == "ligolo":
            from mudale_engine.adapters.ligolo import LigoloAdapter
            desc = LigoloAdapter.describe(parsed)
        else:
            from mudale_engine.adapters.ssh import SshAdapter
            desc = SshAdapter.describe(parsed)
        output.success(f"Tunnel {rec.id} active — {desc}")
        print(output.paint("  Tunnel running in foreground. Press Ctrl+C to stop.", "grey"))
        try:
            while True:
                engine.reap_tunnels()
                if rec.id not in engine._tunnels:
                    updated = engine.db.get_tunnel(rec.id)
                    output.error(f"Tunnel died: {updated.last_error if updated else 'unknown'}")
                    return EXIT_ERROR
                time.sleep(2.0)
        except KeyboardInterrupt:
            print()
            engine.stop_tunnel(rec.id)
            output.success(f"Tunnel {rec.id} stopped")
    else:
        updated = engine.db.get_tunnel(rec.id)
        output.error(f"Tunnel failed: {updated.last_error if updated else 'unknown'}")
        return EXIT_ERROR
    return EXIT_OK


def cmd_oneshot_scan_run(args) -> int:
    from mudale_core.supervisor import Engine
    from mudale_engine.enums import ScanStatus

    engine = Engine()
    ws = engine.db.ensure_default_workspace()

    rec = engine.db.create_scan(ws.id, args.target, args.profile, via_tunnel_id=args.via_tunnel)
    success = engine.start_scan(rec.id)
    if not success:
        updated = engine.db.get_scan(rec.id)
        output.error(f"Scan failed: {updated.error if updated else 'unknown'}")
        return EXIT_ERROR

    print(f"Scanning {args.target} ({args.profile})...")
    while rec.id in engine._scans:
        engine.reap_scans()
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(1.0)
    print()

    updated = engine.db.get_scan(rec.id)
    if updated and updated.status == ScanStatus.COMPLETED:
        output.success(f"{updated.hosts_up} hosts up, {updated.services_found} services found")
        services = engine.db.list_services(scan_id=rec.id)
        if services:
            output.table(
                [{"host": s.host, "port": f"{s.port}/{s.protocol}", "service": s.service_name,
                  "product": s.product, "version": s.version} for s in services],
                [("host", "HOST"), ("port", "PORT"), ("service", "SERVICE"),
                 ("product", "PRODUCT"), ("version", "VERSION")],
            )
    else:
        output.error(f"Scan {updated.status}: {updated.error}" if updated else "Scan failed")
        return EXIT_ERROR
    return EXIT_OK


def cmd_oneshot_jobs(args) -> int:
    from mudale_core.state import StateDB
    from mudale_engine.adapters.ssh import SshAdapter
    from mudale_engine.specs import SpecError, parse_spec

    db = StateDB()
    tunnels = db.list_tunnels()
    if not tunnels:
        print(output.paint("No tunnels.", "grey"))
        return EXIT_OK

    rows = []
    for t in tunnels:
        try:
            spec = parse_spec(t.kind, t.spec)
            if t.kind == "ligolo":
                from mudale_engine.adapters.ligolo import LigoloAdapter
                desc = LigoloAdapter.describe(spec)
            else:
                desc = SshAdapter.describe(spec)
        except (SpecError, TypeError):
            desc = t.kind
        rows.append({
            "id": t.id, "type": t.kind,
            "status": output.status_label(t.status), "description": desc,
        })

    columns = [("id", "ID"), ("type", "TYPE"), ("status", "STATUS"), ("description", "ROUTE")]
    output.table(rows, columns)
    return EXIT_OK


def cmd_oneshot_services(args) -> int:
    from mudale_core.state import StateDB

    db = StateDB()
    services = db.list_services()
    if not services:
        print(output.paint("No services discovered yet.", "grey"))
        return EXIT_OK

    output.table(
        [{"host": s.host, "port": f"{s.port}/{s.protocol}", "service": s.service_name,
          "product": s.product, "version": s.version} for s in services],
        [("host", "HOST"), ("port", "PORT"), ("service", "SERVICE"),
         ("product", "PRODUCT"), ("version", "VERSION")],
    )
    return EXIT_OK


def cmd_oneshot_kill(args) -> int:
    from mudale_core.supervisor import Engine

    engine = Engine()
    success = engine.stop_tunnel(args.id)
    if success:
        output.success(f"Tunnel {args.id} stopped")
    else:
        output.error(f"Failed to stop tunnel {args.id}")
    return EXIT_OK if success else EXIT_ERROR


# ── Remote client commands (original REST API) ─────────────────────────


def cmd_remote_login(args) -> int:
    config = Config(args.url, args.token)
    client = Client(config)
    me = client.get("/me/")
    config.save()
    output.success(
        f"Signed in to {config.url} as {me['username']} ({me['role']}). "
        f"Config saved to ~/.config/mudale/config.json"
    )
    return EXIT_OK


def cmd_remote_tunnels(args) -> int:
    rows = Client().paged("/tunnels/", {"engagement": getattr(args, "engagement", None)})
    if getattr(args, "json", False):
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["uptime"] = output.duration(row.get("uptime_seconds"))
    output.table(
        rows,
        [("id", "ID"), ("status", "STATUS"), ("kind", "KIND"),
         ("description", "ROUTE"), ("uptime", "UPTIME"), ("pid", "PID")],
        empty="No tunnels.",
    )
    return EXIT_OK


def cmd_remote_scans(args) -> int:
    rows = Client().paged("/scans/", {"engagement": getattr(args, "engagement", None)})
    if getattr(args, "json", False):
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["when"] = output.relative_time(row["queued_at"])
    output.table(
        rows,
        [("id", "ID"), ("status", "STATUS"), ("profile", "PROFILE"),
         ("target", "TARGET"), ("services_found", "SERVICES"), ("when", "QUEUED")],
        empty="No scans.",
    )
    return EXIT_OK


def cmd_remote_status(args) -> int:
    client = Client()
    health = client.get("/health/")
    engine = client.get("/engine/status/")
    output.detail([
        ("server", client.config.url),
        ("api", output.status_label("ok" if health.get("status") == "ok" else "error")),
        ("engine", output.status_label("ok" if engine["attached"] else "error")),
    ])
    return EXIT_OK


# ── Parser ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mudale",
        description=(
            "MudaleTunnel — SSH tunnels, nmap scanning, network pivoting.\n\n"
            "Run with no arguments for the interactive console."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Console (default when no command given)
    console_p = subparsers.add_parser("console", help="Interactive console (msfconsole-style)")
    console_p.set_defaults(handler=cmd_console)

    # Server
    server_p = subparsers.add_parser("server", help="Start the web dashboard")
    server_p.set_defaults(handler=cmd_server)
    server_p.add_argument("--port", type=int, default=8000)
    server_p.add_argument("--bind", default="127.0.0.1")

    # Daemon
    daemon_p = subparsers.add_parser("daemon", help="Background daemon management")
    daemon_p.set_defaults(handler=cmd_daemon)
    daemon_sub = daemon_p.add_subparsers(dest="daemon_action")
    daemon_sub.add_parser("start", help="Start the background daemon")
    daemon_sub.add_parser("stop", help="Stop the background daemon")
    daemon_sub.add_parser("status", help="Check daemon status")

    # One-shot: tunnel create
    tunnel_p = subparsers.add_parser("tunnel", help="Tunnel operations")
    tunnel_sub = tunnel_p.add_subparsers(dest="tunnel_action", required=True)

    tc = tunnel_sub.add_parser("create", help="Create and start a tunnel")
    tc.set_defaults(handler=cmd_oneshot_tunnel_create)
    tc.add_argument(
        "--type", "-t", required=True,
        choices=["ssh_local", "ssh_dynamic", "ssh_remote", "ssh_remote_dynamic", "ligolo"],
    )
    tc.add_argument("--rhost", required=True, help="Target SSH host")
    tc.add_argument("--rport", type=int, default=22, help="Target SSH port")
    tc.add_argument("--username", "-u", default="root", help="SSH username")
    tc.add_argument("--identity", "-i", help="SSH private key path")
    tc.add_argument("--insecure", action="store_true", help="Accept unknown host keys")
    tc.add_argument("--lhost", default="127.0.0.1", help="Local bind address")
    tc.add_argument("--lport", type=int, help="Local port")
    tc.add_argument("--target-host", help="Remote target host (for local/remote forward)")
    tc.add_argument("--target-port", type=int, help="Remote target port")
    tc.add_argument("--remote-bind", default="127.0.0.1")
    tc.add_argument("--remote-port", type=int)
    tc.add_argument("--tun-name", default="ligolo",
                    help="TUN interface name (ligolo only)")
    tc.add_argument("--no-selfcert", action="store_true",
                    help="Disable self-signed cert (ligolo only)")
    tc.add_argument("--label", default="")
    tc.add_argument("--workspace", "-w")

    # One-shot: scan run
    scan_p = subparsers.add_parser("scan", help="Scan operations")
    scan_sub = scan_p.add_subparsers(dest="scan_action", required=True)

    sr = scan_sub.add_parser("run", help="Run an nmap scan")
    sr.set_defaults(handler=cmd_oneshot_scan_run)
    sr.add_argument("--target", required=True, help="Target IP/CIDR")
    sr.add_argument("--profile", default="standard",
                    choices=["discovery", "quick", "standard", "full", "udp_top"])
    sr.add_argument("--via-tunnel", type=int, help="Route scan through tunnel ID")

    # One-shot: jobs, services, kill
    jobs_p = subparsers.add_parser("jobs", help="List active tunnels and scans")
    jobs_p.set_defaults(handler=cmd_oneshot_jobs)

    services_p = subparsers.add_parser("services", help="List discovered services")
    services_p.set_defaults(handler=cmd_oneshot_services)

    kill_p = subparsers.add_parser("kill", help="Stop a tunnel")
    kill_p.set_defaults(handler=cmd_oneshot_kill)
    kill_p.add_argument("id", type=int, help="Tunnel ID to stop")

    # Remote: connect to a MudaleTunnel server
    remote_p = subparsers.add_parser("remote", help="Connect to a remote MudaleTunnel server")
    remote_sub = remote_p.add_subparsers(dest="remote_action", required=True)

    rl = remote_sub.add_parser("login", help="Store server URL and API key")
    rl.set_defaults(handler=cmd_remote_login)
    rl.add_argument("--url", default="http://127.0.0.1:8000")
    rl.add_argument("--token", required=True)

    rt = remote_sub.add_parser("tunnels", help="List tunnels on remote server")
    rt.set_defaults(handler=cmd_remote_tunnels)
    rt.add_argument("--engagement", type=int)
    rt.add_argument("--json", action="store_true")

    rs = remote_sub.add_parser("scans", help="List scans on remote server")
    rs.set_defaults(handler=cmd_remote_scans)
    rs.add_argument("--engagement", type=int)
    rs.add_argument("--json", action="store_true")

    rst = remote_sub.add_parser("status", help="Remote server status")
    rst.set_defaults(handler=cmd_remote_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        return cmd_console(args)

    if not hasattr(args, "handler"):
        parser.print_help()
        return EXIT_OK

    try:
        return args.handler(args)
    except ValueError as exc:
        output.error(str(exc))
        return EXIT_ERROR
    except ApiError as exc:
        if exc.status == 0:
            output.error(exc.detail)
            return EXIT_UNREACHABLE
        if exc.status in (401, 403):
            output.error(exc.detail)
            return EXIT_DENIED
        output.error(exc.detail)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
