"""Pivot tests — reachability, exposure and client config."""

from __future__ import annotations

import pytest

from apps.agents.models import Agent, EngineKind
from apps.scans.models import Scan, ScanProfile, ScanStatus, Service
from apps.tunnels import pivot
from apps.tunnels.models import Tunnel, TunnelKind, TunnelStatus

pytestmark = pytest.mark.django_db


SOCKS_SPEC = {
    "endpoint": {"user": "opsec", "host": "10.4.0.10", "port": 22},
    "local_bind": "127.0.0.1",
    "local_port": 1080,
}


@pytest.fixture
def agent(engagement):
    return Agent.objects.create(engagement=engagement, engine=EngineKind.SSH, name="dmz-jump")


@pytest.fixture
def socks(engagement, agent):
    return Tunnel.objects.create(
        engagement=engagement,
        agent=agent,
        kind=TunnelKind.SSH_DYNAMIC,
        label="dmz socks",
        spec=SOCKS_SPEC,
        status=TunnelStatus.ACTIVE,
    )


def add_findings(engagement, *, via, findings):
    """Record a completed scan and the services it found."""
    scan = Scan.objects.create(
        engagement=engagement,
        target="10.4.9.0/24",
        profile=ScanProfile.QUICK,
        via_tunnel=via,
        status=ScanStatus.COMPLETED,
    )
    for host, port, name in findings:
        Service.objects.create(
            scan=scan, engagement=engagement, host=host, port=port,
            state=Service.State.OPEN, service_name=name,
        )
    return scan


# ── Reachability ────────────────────────────────────────────────────────


def test_map_separates_direct_from_pivoted(engagement, socks):
    add_findings(engagement, via=None, findings=[("10.4.0.10", 22, "ssh")])
    add_findings(
        engagement, via=socks,
        findings=[("10.4.9.5", 1433, "ms-sql-s"), ("10.4.9.5", 445, "microsoft-ds")],
    )

    result = pivot.build_map(engagement)

    assert [h.host for h in result.direct] == ["10.4.0.10"]
    behind = result.by_tunnel[socks.pk]
    assert [h.host for h in behind] == ["10.4.9.5"]
    assert sorted(behind[0].open_ports) == [445, 1433]


def test_map_summarises_the_subnets_a_pivot_opens(engagement, socks):
    add_findings(
        engagement, via=socks,
        findings=[("10.4.9.5", 443, "https"), ("10.4.50.9", 80, "http")],
    )
    result = pivot.build_map(engagement)
    assert result.subnets_by_tunnel[socks.pk] == ["10.4.50.0/24", "10.4.9.0/24"]


def test_closed_ports_do_not_count_as_reachable(engagement, socks):
    scan = add_findings(engagement, via=socks, findings=[])
    Service.objects.create(
        scan=scan, engagement=engagement, host="10.4.9.5", port=1433,
        state=Service.State.FILTERED,
    )
    assert pivot.build_map(engagement).total_hosts == 0


def test_reachability_is_recorded_on_the_agent(engagement, socks, agent):
    """A tunnelled scan is evidence of what that foothold can see."""
    scan = add_findings(engagement, via=socks, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    pivot.refresh_agent_reachability(scan)

    agent.refresh_from_db()
    assert agent.reachable_cidrs == ["10.4.9.0/24"]


def test_a_direct_scan_teaches_nothing_about_a_pivot(engagement, agent):
    scan = add_findings(engagement, via=None, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    assert pivot.refresh_agent_reachability(scan) == []
    agent.refresh_from_db()
    assert agent.reachable_cidrs == []


def test_subnet_summary_handles_both_families():
    assert pivot.summarise_subnets(["10.4.9.5", "10.4.9.200"]) == ["10.4.9.0/24"]
    assert pivot.summarise_subnets(["2001:db8::1"]) == ["2001:db8::/64"]
    assert pivot.summarise_subnets(["not-an-ip"]) == []


# ── Exposing ────────────────────────────────────────────────────────────


def test_exposing_a_service_creates_a_forward_through_its_pivot(engagement, socks, operator):
    scan = add_findings(engagement, via=socks, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    service = Service.objects.get(scan=scan)

    tunnel = pivot.expose_service(service, operator=operator)

    assert tunnel.kind == TunnelKind.SSH_LOCAL
    assert tunnel.spec["target_host"] == "10.4.9.5"
    assert tunnel.spec["target_port"] == 1433
    # Reuses the pivot's SSH endpoint — same jump host, no new credentials.
    assert tunnel.spec["endpoint"]["host"] == "10.4.0.10"
    assert pivot.AUTO_PORT_START <= tunnel.spec["local_port"] <= pivot.AUTO_PORT_END


def test_a_directly_discovered_service_is_refused(engagement, operator):
    """Nothing to pivot through — it is already reachable."""
    scan = add_findings(engagement, via=None, findings=[("10.4.0.10", 22, "ssh")])
    service = Service.objects.get(scan=scan)
    with pytest.raises(pivot.PivotError, match="already reachable"):
        pivot.expose_service(service, operator=operator)


def test_exposing_through_a_non_socks_tunnel_is_refused(engagement, operator, agent):
    forward = Tunnel.objects.create(
        engagement=engagement, agent=agent, kind=TunnelKind.SSH_LOCAL,
        spec={
            "endpoint": {"user": "opsec", "host": "10.4.0.10", "port": 22},
            "local_port": 8080, "target_host": "10.4.9.5", "target_port": 443,
        },
    )
    scan = add_findings(engagement, via=forward, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    service = Service.objects.get(scan=scan)
    with pytest.raises(pivot.PivotError, match="not a SOCKS proxy"):
        pivot.expose_service(service, operator=operator)


def test_allocated_ports_do_not_collide(engagement, socks, operator):
    add_findings(
        engagement, via=socks,
        findings=[("10.4.9.5", 1433, "ms-sql-s"), ("10.4.9.6", 8080, "http")],
    )
    ports = {
        pivot.expose_service(service, operator=operator).spec["local_port"]
        for service in Service.objects.filter(scan__via_tunnel=socks)
    }
    assert len(ports) == 2


def test_an_explicit_local_port_is_honoured(engagement, socks, operator):
    scan = add_findings(engagement, via=socks, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    service = Service.objects.get(scan=scan)
    tunnel = pivot.expose_service(service, operator=operator, local_port=15432)
    assert tunnel.spec["local_port"] == 15432


# ── Auto-expose ─────────────────────────────────────────────────────────


def test_auto_expose_skips_administrative_ports(engagement, socks, operator):
    """Forwarding 22/3389 is legitimate, but must be an explicit decision."""
    add_findings(
        engagement, via=socks,
        findings=[
            ("10.4.9.5", 1433, "ms-sql-s"),
            ("10.4.9.5", 22, "ssh"),
            ("10.4.9.6", 3389, "ms-wbt-server"),
            ("10.4.9.7", 8080, "http"),
        ],
    )
    created = pivot.auto_expose(engagement, tunnel=socks, operator=operator)
    exposed = {(t.spec["target_host"], t.spec["target_port"]) for t in created}

    assert ("10.4.9.5", 1433) in exposed
    assert ("10.4.9.7", 8080) in exposed
    assert ("10.4.9.5", 22) not in exposed
    assert ("10.4.9.6", 3389) not in exposed


def test_sensitive_ports_can_be_opted_into(engagement, socks, operator):
    add_findings(engagement, via=socks, findings=[("10.4.9.5", 22, "ssh")])
    created = pivot.auto_expose(
        engagement, tunnel=socks, operator=operator, include_sensitive=True
    )
    assert len(created) == 1


def test_auto_expose_is_bounded(engagement, socks, operator):
    """One command must not be able to open a hundred ports by accident."""
    add_findings(
        engagement, via=socks,
        findings=[(f"10.4.9.{i}", 8080, "http") for i in range(1, 40)],
    )
    created = pivot.auto_expose(engagement, tunnel=socks, operator=operator, limit=5)
    assert len(created) == 5


def test_auto_expose_does_not_duplicate_existing_forwards(engagement, socks, operator):
    add_findings(engagement, via=socks, findings=[("10.4.9.5", 1433, "ms-sql-s")])

    first = pivot.auto_expose(engagement, tunnel=socks, operator=operator)
    second = pivot.auto_expose(engagement, tunnel=socks, operator=operator)

    assert len(first) == 1
    assert second == []


def test_auto_expose_can_filter_to_specific_ports(engagement, socks, operator):
    add_findings(
        engagement, via=socks,
        findings=[("10.4.9.5", 1433, "ms-sql-s"), ("10.4.9.6", 8080, "http")],
    )
    created = pivot.auto_expose(engagement, tunnel=socks, operator=operator, ports=[1433])
    assert len(created) == 1
    assert created[0].spec["target_port"] == 1433


def test_exposed_targets_are_still_scope_checked(engagement, socks, operator):
    """expose_service goes through create_tunnel, so scope still applies."""
    from apps.engagements.scope import OutOfScope

    scan = add_findings(engagement, via=socks, findings=[("10.4.9.5", 1433, "ms-sql-s")])
    service = Service.objects.get(scan=scan)

    engagement.authorized_cidrs = ["192.168.50.0/24"]
    engagement.save(update_fields=["authorized_cidrs"])

    with pytest.raises(OutOfScope):
        pivot.expose_service(service, operator=operator)


# ── proxychains ─────────────────────────────────────────────────────────


def test_proxychains_config_points_at_the_socks_port(socks):
    config = pivot.proxychains_config(socks)
    assert "socks5 127.0.0.1 1080" in config
    assert "strict_chain" in config
    # The guidance matters as much as the config: a SYN scan cannot work here.
    assert "-sT" in config


def test_proxychains_is_refused_for_a_non_socks_tunnel(engagement, agent):
    forward = Tunnel.objects.create(
        engagement=engagement, agent=agent, kind=TunnelKind.SSH_LOCAL, spec={}
    )
    with pytest.raises(pivot.PivotError, match="not a SOCKS proxy"):
        pivot.proxychains_config(forward)
