"""The ``mudale`` command-line client.

    mudale login --url http://localhost:8000 --token mdlt_...
    mudale engagements
    mudale tunnels
    mudale tunnel create --engagement 1 --kind ssh_dynamic --ssh-user opsec \\
        --ssh-host 10.4.0.10 --local-port 1080
    mudale tunnel logs 3 --follow
    mudale scan run --engagement 1 --target 10.4.9.0/24 --via-tunnel 3 --wait
    mudale pivot map --engagement 1
    mudale pivot expose 42

Everything here goes through the REST API, so a tunnel opened from the terminal
shows up in the dashboard the moment it is created — same writes, same policy
checks, same audit trail.
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


# ── Auth ────────────────────────────────────────────────────────────────


def cmd_login(args) -> int:
    config = Config(args.url, args.token)
    client = Client(config)
    me = client.get("/me/")
    config.save()
    output.success(
        f"Signed in to {config.url} as {me['username']} ({me['role']}). "
        f"Config saved to ~/.config/mudale/config.json"
    )
    return EXIT_OK


def cmd_whoami(args) -> int:
    me = Client().get("/me/")
    if args.json:
        output.print_json(me)
        return EXIT_OK
    output.detail(
        [
            ("user", me["username"]),
            ("callsign", me["callsign"]),
            ("role", me["role"]),
            ("can write", me["can_mutate"]),
        ]
    )
    return EXIT_OK


def cmd_status(args) -> int:
    client = Client()
    health = client.get("/health/")
    engine = client.get("/engine/status/")

    if args.json:
        output.print_json({"health": health, "engine": engine})
        return EXIT_OK

    output.detail(
        [
            ("server", client.config.url),
            ("api", output.status_label("ok" if health.get("status") == "ok" else "error")),
            (
                "engine",
                output.status_label("ok" if engine["attached"] else "error")
                + ("" if engine["attached"] else "  no engine daemon is attached"),
            ),
        ]
    )
    for instance in engine["instances"]:
        capabilities = ", ".join(k for k, v in instance["capabilities"].items() if v) or "none"
        print(
            f"  {instance['instance_id']} on {instance['hostname']} "
            f"({capabilities}) — {output.relative_time(instance['last_heartbeat_at'])}"
        )
    return EXIT_OK


# ── Engagements ─────────────────────────────────────────────────────────


def cmd_engagements(args) -> int:
    rows = Client().paged("/engagements/")
    if args.json:
        output.print_json(rows)
        return EXIT_OK

    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["scope"] = ", ".join(row["authorized_cidrs"]) or output.paint("none — inert", "red")
    output.table(
        rows,
        [
            ("id", "ID"), ("name", "NAME"), ("client", "CLIENT"), ("status", "STATUS"),
            ("scope", "AUTHORISED SCOPE"), ("tunnel_count", "TUNNELS"),
        ],
        empty="No engagements. Create one with: mudale engagement create --name ... --cidr ...",
    )
    return EXIT_OK


def cmd_engagement_create(args) -> int:
    body = {
        "name": args.name,
        "slug": args.slug or args.name.lower().replace(" ", "-")[:64],
        "client": args.client or "",
        "status": args.status,
        "authorized_cidrs": args.cidr or [],
    }
    engagement = Client().post("/engagements/", body)
    output.success(f"Created engagement {engagement['id']} ({engagement['slug']})")
    if not engagement["authorized_cidrs"]:
        print(
            output.paint(
                "  No authorised CIDRs, so every target is out of scope. "
                "Add some with: mudale engagement scope <id> --cidr 10.4.0.0/16",
                "yellow",
            )
        )
    return EXIT_OK


def cmd_engagement_scope(args) -> int:
    client = Client()
    current = client.get(f"/engagements/{args.id}/")
    updated = client.patch(f"/engagements/{args.id}/", {"authorized_cidrs": args.cidr})
    output.success(
        f"Scope: {current['authorized_cidrs']} → {updated['authorized_cidrs']}"
    )
    return EXIT_OK


# ── Tunnels ─────────────────────────────────────────────────────────────


def cmd_tunnels(args) -> int:
    rows = Client().paged("/tunnels/", {"engagement": args.engagement, "status": args.status})
    if args.json:
        output.print_json(rows)
        return EXIT_OK

    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["uptime"] = output.duration(row.get("uptime_seconds"))
    output.table(
        rows,
        [
            ("id", "ID"), ("status", "STATUS"), ("kind", "KIND"),
            ("description", "ROUTE"), ("uptime", "UPTIME"), ("pid", "PID"),
        ],
        empty="No tunnels yet.",
    )
    return EXIT_OK


def _build_spec(args) -> dict:
    """Assemble the engine spec from CLI flags.

    Shape only — the server re-validates and scope-checks it, so a malformed or
    out-of-scope spec is refused there rather than trusted from the client.
    """
    endpoint = {"user": args.ssh_user, "host": args.ssh_host, "port": args.ssh_port}
    if args.identity_file:
        endpoint["identity_file"] = args.identity_file
    if args.insecure_host_key:
        endpoint["strict_host_key_checking"] = False

    if args.kind == "ssh_dynamic":
        return {"endpoint": endpoint, "local_port": args.local_port, "local_bind": args.local_bind}
    if args.kind == "ssh_local":
        return {
            "endpoint": endpoint,
            "local_bind": args.local_bind,
            "local_port": args.local_port,
            "target_host": args.target_host,
            "target_port": args.target_port,
        }
    if args.kind == "ssh_remote":
        return {
            "endpoint": endpoint,
            "remote_bind": args.remote_bind,
            "remote_port": args.remote_port,
            "target_host": args.target_host,
            "target_port": args.target_port,
        }
    if args.kind == "ssh_remote_dynamic":
        return {
            "endpoint": endpoint,
            "remote_bind": args.remote_bind,
            "remote_port": args.remote_port,
        }
    raise SystemExit(f"Unsupported kind {args.kind!r}")


def cmd_tunnel_create(args) -> int:
    tunnel = Client().post(
        "/tunnels/",
        {
            "engagement": args.engagement,
            "kind": args.kind,
            "label": args.label or "",
            "spec": _build_spec(args),
        },
    )
    output.success(f"Tunnel {tunnel['id']} requested: {tunnel['description']}")
    print(output.paint("  The engine will bring it up; watch with: mudale tunnels", "grey"))
    return EXIT_OK


def cmd_tunnel_show(args) -> int:
    tunnel = Client().get(f"/tunnels/{args.id}/")
    if args.json:
        output.print_json(tunnel)
        return EXIT_OK

    output.detail(
        [
            ("id", tunnel["id"]),
            ("label", tunnel["label"]),
            ("kind", tunnel["kind_display"]),
            ("route", tunnel["description"]),
            ("status", output.status_label(tunnel["status"])),
            ("desired", tunnel["desired_state"]),
            ("pid", tunnel["pid"]),
            ("uptime", output.duration(tunnel.get("uptime_seconds"))),
            ("restarts", tunnel["restart_count"]),
            ("error", tunnel["last_error"] or "—"),
        ]
    )
    if tunnel["routes"]:
        print("\nRoutes")
        output.table(tunnel["routes"], [("cidr", "CIDR"), ("status", "STATUS")])
    if tunnel["listeners"]:
        print("\nListeners")
        output.table(
            tunnel["listeners"],
            [("bind_host", "BIND"), ("bind_port", "PORT"), ("to_host", "TO"), ("to_port", "PORT")],
        )
    return EXIT_OK


def cmd_tunnel_stop(args) -> int:
    tunnel = Client().post(f"/tunnels/{args.id}/stop/")
    output.success(f"Stop requested for tunnel {tunnel['id']}")
    return EXIT_OK


def cmd_tunnel_start(args) -> int:
    tunnel = Client().post(f"/tunnels/{args.id}/start/")
    output.success(f"Start requested for tunnel {tunnel['id']}")
    return EXIT_OK


def cmd_tunnel_logs(args) -> int:
    client = Client()
    seen: set[int] = set()

    while True:
        payload = client.get(f"/tunnels/{args.id}/logs/", {"limit": args.limit})
        for entry in payload["results"]:
            if entry["id"] in seen:
                continue
            seen.add(entry["id"])
            stamp = output.paint(entry["created_at"][11:19], "grey")
            level = output.status_label("error" if entry["level"] == "error" else "ok")
            print(f"{stamp} {level:<8} {entry['message']}")

        if not args.follow:
            return EXIT_OK
        time.sleep(POLL_INTERVAL)


def cmd_pivot_map(args) -> int:
    """Show what is reachable and through which pivot."""
    client = Client()
    data = client.get("/pivot/map/", {"engagement": args.engagement})

    if args.json:
        output.print_json(data)
        return EXIT_OK

    print(f"{data['total_hosts']} hosts reachable\n")

    if data["direct"]:
        print(output.paint("direct", "bold"))
        for host in data["direct"]:
            ports = ", ".join(str(p) for p in host["open_ports"])
            print(f"  {host['host']:<16} {ports}")
        print()

    for entry in data["pivots"]:
        header = f"via tunnel {entry['tunnel']} — {entry['label']}"
        print(output.paint(header, "bold"))
        if entry["subnets"]:
            print(output.paint(f"  opens: {', '.join(entry['subnets'])}", "grey"))
        for host in entry["hosts"]:
            ports = ", ".join(str(p) for p in host["open_ports"])
            name = f" ({host['hostname']})" if host["hostname"] else ""
            print(f"  {host['host']:<16}{name} {ports}")
        print()

    if not data["direct"] and not data["pivots"]:
        print(output.paint("Nothing discovered yet. Run a scan first.", "grey"))
    return EXIT_OK


def cmd_pivot_expose(args) -> int:
    """Turn a discovered service into a local forward."""
    tunnel = Client().post(
        f"/services/{args.service}/expose/",
        {"local_port": args.local_port, "label": args.label or ""},
    )
    output.success(f"Tunnel {tunnel['id']}: {tunnel['description']}")
    return EXIT_OK


def cmd_pivot_auto(args) -> int:
    """Expose everything a pivot found, in one go."""
    result = Client().post(
        f"/tunnels/{args.tunnel}/auto-expose/",
        {"include_sensitive": args.include_sensitive, "limit": args.limit},
    )
    if not result["count"]:
        print(output.paint("Nothing new to expose.", "grey"))
        return EXIT_OK

    output.success(f"Exposed {result['count']} services")
    for tunnel in result["created"]:
        print(f"  {tunnel['description']}")
    return EXIT_OK


def cmd_pivot_proxychains(args) -> int:
    """Print a proxychains config for a SOCKS pivot."""
    config = Client().get(f"/tunnels/{args.tunnel}/proxychains/")["config"]
    if args.output:
        with open(args.output, "w") as handle:
            handle.write(config)
        output.success(f"Wrote {args.output}")
        print(output.paint(f"  proxychains4 -f {args.output} nmap -sT -Pn <target>", "grey"))
        return EXIT_OK
    print(config, end="")
    return EXIT_OK


# ── Scans ───────────────────────────────────────────────────────────────


def cmd_scan_run(args) -> int:
    client = Client()
    scan = client.post(
        "/scans/",
        {
            "engagement": args.engagement,
            "target": args.target,
            "profile": args.profile,
            "via_tunnel": args.via_tunnel,
        },
    )
    output.success(f"Scan {scan['id']} queued: {scan['profile']} of {scan['target']}")

    if not args.wait:
        return EXIT_OK

    while True:
        time.sleep(POLL_INTERVAL)
        scan = client.get(f"/scans/{scan['id']}/")
        if scan["status"] in {"completed", "failed", "cancelled", "timed_out"}:
            break
        print(output.paint(f"  {scan['status']}...", "grey"))

    if scan["status"] != "completed":
        output.error(f"Scan {scan['status']}: {scan['error']}")
        return EXIT_ERROR

    print(
        f"\n{scan['services_found']} services on {scan['hosts_up']} hosts "
        f"in {output.duration(scan.get('duration_seconds'))}\n"
    )
    return _print_services(client, scan["id"], as_json=args.json)


def cmd_scans(args) -> int:
    rows = Client().paged("/scans/", {"engagement": args.engagement})
    if args.json:
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["when"] = output.relative_time(row["queued_at"])
    output.table(
        rows,
        [
            ("id", "ID"), ("status", "STATUS"), ("profile", "PROFILE"),
            ("target", "TARGET"), ("services_found", "SERVICES"), ("when", "QUEUED"),
        ],
        empty="No scans yet.",
    )
    return EXIT_OK


def cmd_scan_services(args) -> int:
    return _print_services(Client(), args.id, as_json=args.json)


def _print_services(client: Client, scan_id: int, *, as_json: bool) -> int:
    rows = client.paged(f"/scans/{scan_id}/services/")
    if as_json:
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["state"] = output.status_label("active" if row["state"] == "open" else "pending")
        row["port"] = f"{row['port']}/{row['protocol']}"
    output.table(
        rows,
        [
            ("id", "ID"), ("host", "HOST"), ("port", "PORT"), ("state", "STATE"),
            ("service_name", "SERVICE"), ("banner", "VERSION"),
        ],
        empty="No open services found.",
    )
    return EXIT_OK


# ── Agents and audit ────────────────────────────────────────────────────


def cmd_agents(args) -> int:
    rows = Client().paged("/agents/", {"engagement": args.engagement})
    if args.json:
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["status"] = output.status_label(row["status"])
        row["seen"] = output.relative_time(row["last_seen_at"])
    output.table(
        rows,
        [
            ("id", "ID"), ("name", "NAME"), ("engine", "ENGINE"), ("status", "STATUS"),
            ("remote_host", "HOST"), ("operating_system", "OS"), ("seen", "LAST SEEN"),
        ],
        empty="No agents registered.",
    )
    return EXIT_OK


def cmd_audit(args) -> int:
    rows = Client().paged(
        "/audit/", {"engagement": args.engagement, "result": args.result, "limit": args.limit}
    )
    if args.json:
        output.print_json(rows)
        return EXIT_OK
    for row in rows:
        row["result"] = output.status_label(row["result"])
        row["when"] = output.relative_time(row["created_at"])
    output.table(
        rows,
        [
            ("when", "WHEN"), ("actor_label", "ACTOR"), ("action", "ACTION"),
            ("result", "RESULT"), ("object_label", "OBJECT"), ("message", "DETAIL"),
        ],
        empty="No audit events.",
    )
    return EXIT_OK


# ── Parser ──────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mudale",
        description="MudaleTunnel — control plane for network pivoting.",
        epilog="Actions taken here appear live in the web dashboard.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str, handler):
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        return sub

    login = add("login", "Store the server URL and API key.", cmd_login)
    login.add_argument("--url", default="http://127.0.0.1:8000")
    login.add_argument("--token", required=True, help="An API key (mdlt_...).")

    add("whoami", "Show the authenticated operator.", cmd_whoami)
    add("status", "Show API and engine health.", cmd_status)

    # Engagements
    add("engagements", "List engagements.", cmd_engagements)
    engagement = subparsers.add_parser("engagement", help="Manage an engagement.")
    engagement_sub = engagement.add_subparsers(dest="subcommand", required=True)

    create = engagement_sub.add_parser("create", help="Create an engagement.")
    create.set_defaults(handler=cmd_engagement_create)
    create.add_argument("--name", required=True)
    create.add_argument("--slug")
    create.add_argument("--client")
    create.add_argument(
        "--status", default="active", choices=["planned", "active", "paused", "closed"]
    )
    create.add_argument("--cidr", action="append", help="Authorised CIDR. Repeatable.")

    scope = engagement_sub.add_parser("scope", help="Replace the authorised CIDR list.")
    scope.set_defaults(handler=cmd_engagement_scope)
    scope.add_argument("id", type=int)
    scope.add_argument("--cidr", action="append", required=True)

    # Tunnels
    tunnels = add("tunnels", "List tunnels.", cmd_tunnels)
    tunnels.add_argument("--engagement", type=int)
    tunnels.add_argument("--status")

    tunnel = subparsers.add_parser("tunnel", help="Manage a tunnel.")
    tunnel_sub = tunnel.add_subparsers(dest="subcommand", required=True)

    tcreate = tunnel_sub.add_parser("create", help="Request a new tunnel.")
    tcreate.set_defaults(handler=cmd_tunnel_create)
    tcreate.add_argument("--engagement", type=int, required=True)
    tcreate.add_argument(
        "--kind",
        required=True,
        choices=["ssh_local", "ssh_dynamic", "ssh_remote", "ssh_remote_dynamic"],
    )
    tcreate.add_argument("--label", default="")
    tcreate.add_argument("--ssh-user", required=True)
    tcreate.add_argument("--ssh-host", required=True)
    tcreate.add_argument("--ssh-port", type=int, default=22)
    tcreate.add_argument("--identity-file")
    tcreate.add_argument(
        "--insecure-host-key",
        action="store_true",
        help="Accept an unknown host key on first connect (accept-new).",
    )
    tcreate.add_argument("--local-bind", default="127.0.0.1")
    tcreate.add_argument("--local-port", type=int)
    tcreate.add_argument("--remote-bind", default="127.0.0.1")
    tcreate.add_argument("--remote-port", type=int)
    tcreate.add_argument("--target-host")
    tcreate.add_argument("--target-port", type=int)

    tshow = tunnel_sub.add_parser("show", help="Show one tunnel.")
    tshow.set_defaults(handler=cmd_tunnel_show)
    tshow.add_argument("id", type=int)

    tstop = tunnel_sub.add_parser("stop", help="Ask the engine to stop a tunnel.")
    tstop.set_defaults(handler=cmd_tunnel_stop)
    tstop.add_argument("id", type=int)

    tstart = tunnel_sub.add_parser("start", help="Ask the engine to start a tunnel.")
    tstart.set_defaults(handler=cmd_tunnel_start)
    tstart.add_argument("id", type=int)

    tlogs = tunnel_sub.add_parser("logs", help="Show engine logs for a tunnel.")
    tlogs.set_defaults(handler=cmd_tunnel_logs)
    tlogs.add_argument("id", type=int)
    tlogs.add_argument("--limit", type=int, default=200)
    tlogs.add_argument("-f", "--follow", action="store_true")

    # Pivoting
    pivot_parser = subparsers.add_parser("pivot", help="Work with what a pivot can reach.")
    pivot_sub = pivot_parser.add_subparsers(dest="subcommand", required=True)

    pmap = pivot_sub.add_parser("map", help="Show reachability, per pivot.")
    pmap.set_defaults(handler=cmd_pivot_map)
    pmap.add_argument("--engagement", type=int, required=True)

    pexpose = pivot_sub.add_parser("expose", help="Forward one discovered service locally.")
    pexpose.set_defaults(handler=cmd_pivot_expose)
    pexpose.add_argument("service", type=int, help="Service id from `mudale scan services`.")
    pexpose.add_argument("--local-port", type=int)
    pexpose.add_argument("--label", default="")

    pauto = pivot_sub.add_parser("auto", help="Forward everything a pivot found.")
    pauto.set_defaults(handler=cmd_pivot_auto)
    pauto.add_argument("tunnel", type=int, help="The SOCKS tunnel to expand.")
    pauto.add_argument("--limit", type=int, default=20)
    pauto.add_argument(
        "--include-sensitive",
        action="store_true",
        help="Also forward 22/3389/5985/623, which are skipped by default.",
    )

    pchains = pivot_sub.add_parser("proxychains", help="Emit a proxychains config.")
    pchains.set_defaults(handler=cmd_pivot_proxychains)
    pchains.add_argument("tunnel", type=int)
    pchains.add_argument("-o", "--output", help="Write to a file instead of stdout.")

    # Scans
    scans = add("scans", "List scans.", cmd_scans)
    scans.add_argument("--engagement", type=int)

    scan = subparsers.add_parser("scan", help="Run and inspect scans.")
    scan_sub = scan.add_subparsers(dest="subcommand", required=True)

    srun = scan_sub.add_parser("run", help="Queue a scan.")
    srun.set_defaults(handler=cmd_scan_run)
    srun.add_argument("--engagement", type=int, required=True)
    srun.add_argument("--target", required=True, help="IP or CIDR, inside the engagement scope.")
    srun.add_argument(
        "--profile", default="standard",
        choices=["discovery", "quick", "standard", "full", "udp_top"],
    )
    srun.add_argument("--via-tunnel", type=int)
    srun.add_argument("--wait", action="store_true", help="Block until the scan finishes.")

    sservices = scan_sub.add_parser("services", help="Show services found by a scan.")
    sservices.set_defaults(handler=cmd_scan_services)
    sservices.add_argument("id", type=int)

    # Agents, audit
    agents = add("agents", "List agents.", cmd_agents)
    agents.add_argument("--engagement", type=int)

    audit = add("audit", "Show the audit trail.", cmd_audit)
    audit.add_argument("--engagement", type=int)
    audit.add_argument("--result", choices=["ok", "denied", "error"])
    audit.add_argument("--limit", type=int, default=50)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False

    try:
        return args.handler(args)
    except ValueError as exc:
        # Bad MUDALE_URL and similar configuration mistakes.
        output.error(str(exc))
        return EXIT_ERROR
    except ApiError as exc:
        if exc.status == 0:
            output.error(exc.detail)
            return EXIT_UNREACHABLE
        if exc.status in (401, 403):
            output.error(exc.detail)
            return EXIT_DENIED
        # Scope refusals land here. The message names the rejected target and
        # what the engagement does allow, so it is printed verbatim.
        output.error(exc.detail)
        return EXIT_ERROR
    except KeyboardInterrupt:
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
