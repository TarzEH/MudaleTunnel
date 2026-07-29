"""Populate the database with invented engagements, for screenshots and demos.

    python manage.py seed_sample_data --reset

Every address, hostname and finding here is fiction, in RFC 1918 space that
belongs to nobody. Nothing is scanned and nothing is connected to — the rows are
written directly. This exists so a recording or screenshot can be published
without a real network appearing in it.

Three engagements, so the dashboard has something to show for each state a real
one passes through:

  * **Acme internal** — mid-engagement. A pivot, forwards built from findings,
    a completed scan, a failed tunnel and denied attempts.
  * **Northwind DMZ** — early. One foothold, a scan running, nothing exposed.
  * **Contoso retainer** — closed. Everything stopped, findings kept. What an
    engagement looks like when you come back to it months later.

All three are written as **paused or closed**, which is what makes the sample
survivable. The engine only reconciles operational engagements, so it leaves
these alone; mark one active and it will — correctly — notice that a tunnel
claiming to be running has a PID that does not exist, try to restart it, and
fail. That is the daemon working, not a bug, and it is why invented "live"
tunnels cannot sit in an active engagement.

Refuses to run outside a loopback-only deployment: invented findings in a real
engagement's audit trail would be worse than useless.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.management.commands.seed_demo import Command as SeedDemoCommand
from apps.accounts.models import Operator, Role
from apps.agents.models import Agent, AgentStatus, EngineKind
from apps.audit.context import AuditContext, using
from apps.audit.models import AuditAction, AuditResult
from apps.audit.services import record
from apps.engagements.models import (
    Engagement,
    EngagementMembership,
    EngagementStatus,
    MembershipRole,
)
from apps.scans.models import Scan, ScanProfile, ScanStatus, Service
from apps.tunnels.models import DesiredState, Tunnel, TunnelKind, TunnelLog, TunnelStatus


def endpoint(host: str, user: str = "opsec") -> dict:
    return {"user": user, "host": host, "port": 22}


class Command(BaseCommand):
    help = "Fill the database with invented engagements for screenshots (loopback only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing sample engagements before writing.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not SeedDemoCommand._is_loopback_only():
            raise CommandError(
                "Refusing to write invented findings on a deployment reachable beyond "
                "loopback. This is demo data, not evidence."
            )

        operator = Operator.objects.filter(username="operator").first()
        if operator is None:
            raise CommandError("No 'operator' account. Run `manage.py seed_demo` first.")

        analyst, created = Operator.objects.get_or_create(
            username="analyst",
            defaults={"role": Role.VIEWER, "callsign": "analyst"},
        )
        if created:
            analyst.set_password("mudale-demo-2026")
            analyst.save(update_fields=["password"])

        slugs = ["acme-internal", "northwind-dmz", "contoso-retainer"]
        if options["reset"]:
            # Also drop seed_demo's placeholder engagement, so the two commands
            # together do not leave two engagements with the same display name.
            Engagement.objects.filter(slug__in=[*slugs, "lab"]).delete()

        now = timezone.now()

        self._acme(operator, analyst, now)
        self._northwind(operator, now)
        self._contoso(operator, now)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nWrote {Engagement.objects.filter(slug__in=slugs).count()} sample "
                f"engagements, {Agent.objects.count()} agents, "
                f"{Tunnel.objects.count()} tunnels, {Service.objects.count()} services.\n"
            )
        )
        self.stdout.write("  Every address is invented. Nothing was scanned.")
        self.stdout.write(
            "  Engagements are paused/closed so the engine leaves the sample alone."
        )
        self.stdout.write("  Second account: analyst / mudale-demo-2026 (read-only role).\n")

    # ── Engagement 1: active, mid-engagement ────────────────────────────

    def _acme(self, operator, analyst, now):
        engagement = Engagement.objects.create(
            name="Acme internal",
            slug="acme-internal",
            client="Acme Manufacturing",
            # Paused, so the engine does not try to reconcile invented tunnels.
            status=EngagementStatus.PAUSED,
            authorized_cidrs=["10.4.0.0/16", "192.168.50.0/24"],
            starts_on=(now - timedelta(days=6)).date(),
            ends_on=(now + timedelta(days=8)).date(),
            notes="Internal assessment. Jump host provided by the client.",
            created_by=operator,
        )
        EngagementMembership.objects.create(
            engagement=engagement, operator=operator, role=MembershipRole.LEAD
        )
        EngagementMembership.objects.create(
            engagement=engagement, operator=analyst, role=MembershipRole.OBSERVER
        )

        agent = Agent.objects.create(
            engagement=engagement, engine=EngineKind.SSH, name="dmz-jump",
            status=AgentStatus.ONLINE, remote_host="10.4.0.10", remote_port=22,
            hostname="jump01.corp.local", operating_system="Debian 12",
            architecture="x86_64", remote_username="opsec", is_privileged=False,
            reachable_cidrs=["10.4.9.0/24", "10.4.50.0/24"],
            first_seen_at=now - timedelta(days=5), last_seen_at=now - timedelta(seconds=14),
            created_by=operator,
        )
        Agent.objects.create(
            engagement=engagement, engine=EngineKind.SSH, name="build-runner",
            status=AgentStatus.OFFLINE, remote_host="10.4.50.9", remote_port=22,
            hostname="build.corp.local", operating_system="Ubuntu 22.04",
            architecture="x86_64", remote_username="ci",
            first_seen_at=now - timedelta(days=2), last_seen_at=now - timedelta(hours=9),
            created_by=operator,
        )

        pivot = Tunnel.objects.create(
            engagement=engagement, agent=agent, kind=TunnelKind.SSH_DYNAMIC, label="dmz-jump",
            spec={"endpoint": endpoint("10.4.0.10"), "local_bind": "127.0.0.1",
                  "local_port": 1080},
            desired_state=DesiredState.UP, status=TunnelStatus.ACTIVE, pid=48219,
            owner_engine_id="sample-data", started_at=now - timedelta(hours=2, minutes=41),
            created_by=operator,
        )
        for level, message in [
            ("info", "Starting: SOCKS on 127.0.0.1:1080 via 10.4.0.10"),
            ("info", "Active (pid 48219)"),
            ("info", "Authenticated with publickey /keys/acme.pem"),
            ("warning", "Server refused to allocate a second forward; continuing"),
        ]:
            TunnelLog.objects.create(tunnel=pivot, level=level, message=message)

        scan = Scan.objects.create(
            engagement=engagement, target="10.4.9.0/24", profile=ScanProfile.STANDARD,
            via_tunnel=pivot, status=ScanStatus.COMPLETED, hosts_up=4, services_found=9,
            started_at=now - timedelta(minutes=34), finished_at=now - timedelta(minutes=32),
            requested_by=operator,
        )
        findings = [
            ("10.4.9.5", "sql01.corp.local", 1433, "ms-sql-s", "Microsoft SQL Server",
             "15.00.2000"),
            ("10.4.9.5", "sql01.corp.local", 445, "microsoft-ds", "Samba smbd", "4.17.5"),
            ("10.4.9.5", "sql01.corp.local", 22, "ssh", "OpenSSH", "8.9p1"),
            ("10.4.9.12", "app02.corp.local", 8080, "http", "Apache Tomcat", "9.0.71"),
            ("10.4.9.12", "app02.corp.local", 8443, "https", "Apache Tomcat", "9.0.71"),
            ("10.4.9.12", "app02.corp.local", 5432, "postgresql", "PostgreSQL", "14.9"),
            ("10.4.9.31", "fileshare.corp.local", 445, "microsoft-ds", "Samba smbd", "4.17.5"),
            ("10.4.9.31", "fileshare.corp.local", 139, "netbios-ssn", "Samba smbd", "4.17.5"),
            ("10.4.9.44", "print01.corp.local", 9100, "jetdirect", "HP JetDirect", ""),
        ]
        for host, hostname, port, name, product, version in findings:
            Service.objects.create(
                scan=scan, engagement=engagement, host=host, hostname=hostname, port=port,
                protocol=Service.Protocol.TCP, state=Service.State.OPEN,
                service_name=name, product=product, version=version,
            )

        # Two findings already turned into forwards.
        for label, port, target, target_port, minutes in [
            ("ms-sql-s on 10.4.9.5", 14000, "10.4.9.5", 1433, 28),
            ("http on 10.4.9.12", 14001, "10.4.9.12", 8080, 21),
        ]:
            Tunnel.objects.create(
                engagement=engagement, agent=agent, kind=TunnelKind.SSH_LOCAL, label=label,
                spec={"endpoint": endpoint("10.4.0.10"), "local_bind": "127.0.0.1",
                      "local_port": port, "target_host": target, "target_port": target_port},
                desired_state=DesiredState.UP, status=TunnelStatus.ACTIVE,
                pid=48600 + port % 100, owner_engine_id="sample-data",
                started_at=now - timedelta(minutes=minutes), created_by=operator,
            )

        # A failed one, so the dashboard has a real error state to render.
        Tunnel.objects.create(
            engagement=engagement, agent=agent, kind=TunnelKind.SSH_LOCAL,
            label="rdp on 10.4.9.44",
            spec={"endpoint": endpoint("10.4.0.10"), "local_bind": "127.0.0.1",
                  "local_port": 14002, "target_host": "10.4.9.44", "target_port": 3389},
            desired_state=DesiredState.DOWN, status=TunnelStatus.FAILED, restart_count=3,
            last_error="SSH could not connect or authenticate, or a forward could not be "
                       "bound: connect_to 10.4.9.44 port 3389: Connection refused",
            started_at=now - timedelta(minutes=12), stopped_at=now - timedelta(minutes=11),
            created_by=operator,
        )

        with using(AuditContext(actor=operator, actor_label="operator", source_ip="127.0.0.1")):
            record(AuditAction.ENGAGEMENT_CREATED, engagement=engagement, obj=engagement)
            record(AuditAction.TUNNEL_STARTED, engagement=engagement, obj=pivot,
                   message="SOCKS on 127.0.0.1:1080 via 10.4.0.10")
            record(AuditAction.SCAN_COMPLETED, engagement=engagement, obj=scan,
                   message="9 services on 4 hosts")
            record(AuditAction.SCOPE_DENIED, result=AuditResult.DENIED, engagement=engagement,
                   message="8.8.8.8/32 is not fully contained by any authorised range "
                           "(10.4.0.0/16, 192.168.50.0/24)",
                   payload={"target": "8.8.8.8", "profile": "quick"})
            record(AuditAction.SCOPE_DENIED, result=AuditResult.DENIED, engagement=engagement,
                   message="Target '-oN /tmp/pwned' may not start with '-'",
                   payload={"target": "-oN /tmp/pwned"})

    # ── Engagement 2: active, early ─────────────────────────────────────

    def _northwind(self, operator, now):
        engagement = Engagement.objects.create(
            name="Northwind DMZ", slug="northwind-dmz", client="Northwind Traders",
            status=EngagementStatus.PAUSED, authorized_cidrs=["172.20.8.0/22"],
            starts_on=now.date(), ends_on=(now + timedelta(days=14)).date(),
            notes="External-facing DMZ only. Nothing behind the inner firewall.",
            created_by=operator,
        )
        EngagementMembership.objects.create(
            engagement=engagement, operator=operator, role=MembershipRole.LEAD
        )
        Agent.objects.create(
            engagement=engagement, engine=EngineKind.SSH, name="edge-relay",
            status=AgentStatus.PENDING, remote_host="172.20.8.4", remote_port=22,
            hostname="relay.northwind.example", operating_system="Alpine 3.19",
            architecture="aarch64", remote_username="svc", created_by=operator,
        )
        Scan.objects.create(
            engagement=engagement, target="172.20.8.0/24", profile=ScanProfile.QUICK,
            status=ScanStatus.RUNNING, started_at=now - timedelta(seconds=40),
            requested_by=operator,
        )

    # ── Engagement 3: closed ────────────────────────────────────────────

    def _contoso(self, operator, now):
        engagement = Engagement.objects.create(
            name="Contoso retainer", slug="contoso-retainer", client="Contoso Ltd",
            status=EngagementStatus.CLOSED, authorized_cidrs=["192.168.120.0/24"],
            starts_on=(now - timedelta(days=95)).date(),
            ends_on=(now - timedelta(days=81)).date(),
            notes="Q1 retainer. Report delivered; kept for reference.",
            created_by=operator,
        )
        EngagementMembership.objects.create(
            engagement=engagement, operator=operator, role=MembershipRole.LEAD
        )
        agent = Agent.objects.create(
            engagement=engagement, engine=EngineKind.SSH, name="legacy-jump",
            status=AgentStatus.RETIRED, remote_host="192.168.120.8",
            hostname="oldbox.contoso.example", operating_system="CentOS 7",
            architecture="x86_64", remote_username="audit",
            first_seen_at=now - timedelta(days=95), last_seen_at=now - timedelta(days=81),
            created_by=operator,
        )
        tunnel = Tunnel.objects.create(
            engagement=engagement, agent=agent, kind=TunnelKind.SSH_DYNAMIC,
            label="legacy-jump", spec={"endpoint": endpoint("192.168.120.8", "audit"),
                                       "local_bind": "127.0.0.1", "local_port": 1080},
            desired_state=DesiredState.DOWN, status=TunnelStatus.STOPPED,
            started_at=now - timedelta(days=90), stopped_at=now - timedelta(days=81),
            created_by=operator,
        )
        scan = Scan.objects.create(
            engagement=engagement, target="192.168.120.0/24", profile=ScanProfile.FULL,
            via_tunnel=tunnel, status=ScanStatus.COMPLETED, hosts_up=2, services_found=3,
            started_at=now - timedelta(days=88), finished_at=now - timedelta(days=88),
            requested_by=operator,
        )
        for host, port, name, product, version in [
            ("192.168.120.20", 3389, "ms-wbt-server", "Microsoft Terminal Services", ""),
            ("192.168.120.20", 445, "microsoft-ds", "Windows Server 2012 R2", ""),
            ("192.168.120.51", 161, "snmp", "net-snmp", "5.7.2"),
        ]:
            Service.objects.create(
                scan=scan, engagement=engagement, host=host, port=port,
                protocol=Service.Protocol.TCP, state=Service.State.OPEN,
                service_name=name, product=product, version=version,
            )
