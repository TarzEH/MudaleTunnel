"""Tests for nmap argv construction — the v2 argument-injection regression suite."""

from __future__ import annotations

import ipaddress

import pytest

from mudale_engine.adapters.nmap import PROFILE_ARGS, NmapAdapter
from mudale_engine.enums import ScanProfile


@pytest.fixture
def adapter(monkeypatch):
    instance = NmapAdapter("nmap")
    monkeypatch.setattr(instance, "binary", lambda: "/usr/bin/nmap")
    monkeypatch.setattr(instance, "proxychains_binary", lambda: "/usr/bin/proxychains4")
    return instance


def net(value: str):
    return ipaddress.ip_network(value)


# ── Regression: the v2 argument-injection hole ──────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        "-oN /etc/cron.d/pwn",
        "--script=/tmp/evil.nse",
        "-iL /etc/passwd",
        "10.4.0.1; rm -rf /",
        "",
    ],
)
def test_raw_string_targets_are_refused(adapter, payload):
    """The adapter refuses a string target outright.

    v2 accepted one and appended it to the argv. Here the type check makes the
    whole class of bug unrepresentable — a caller must parse and scope-check
    first, and a parsed object cannot carry a flag.
    """
    with pytest.raises(TypeError, match="must be a parsed ip_network"):
        adapter.plan(target=payload, profile=ScanProfile.QUICK)


def test_target_is_separated_from_options(adapter):
    plan = adapter.plan(target=net("10.4.0.0/24"), profile=ScanProfile.QUICK)
    assert plan.argv[-2] == "--"
    assert plan.argv[-1] == "10.4.0.0/24"


def test_no_profile_can_write_to_the_filesystem(adapter):
    """Output-file and NSE flags must not exist in any profile."""
    forbidden = {
        "-oN", "-oX", "-oG", "-oA", "-oS",
        "--datadir", "--script", "--script-args", "-iL",
    }
    for profile, args in PROFILE_ARGS.items():
        assert not forbidden.intersection(args), f"profile {profile} can touch the filesystem"


def test_unknown_profile_is_refused(adapter):
    with pytest.raises(ValueError, match="Unknown scan profile"):
        adapter.plan(target=net("10.4.0.0/24"), profile="--script=evil")


# ── Profiles ────────────────────────────────────────────────────────────


def test_quick_profile_argv(adapter):
    plan = adapter.plan(target=net("10.4.0.0/24"), profile=ScanProfile.QUICK)
    assert plan.argv[0] == "/usr/bin/nmap"
    assert "-F" in plan.argv
    assert "--open" in plan.argv


def test_default_profiles_use_connect_scan(adapter):
    """A connect() scan is what actually works from an unprivileged pivot."""
    for profile in (ScanProfile.QUICK, ScanProfile.STANDARD, ScanProfile.FULL):
        assert "-sT" in PROFILE_ARGS[profile]
        assert "-sS" not in PROFILE_ARGS[profile]


def test_only_udp_profile_needs_root(adapter):
    assert adapter.requires_root(ScanProfile.UDP_TOP)
    assert not adapter.requires_root(ScanProfile.STANDARD)


def test_tunnelled_scan_tells_nmap_it_is_unprivileged(adapter, tmp_path, settings):
    """Through a SOCKS pivot, nmap's host discovery lies unless told not to."""
    settings.ENGINE = {**settings.ENGINE, "LOG_DIR": str(tmp_path / "logs")}
    plan = adapter.plan(
        target=net("10.4.0.0/24"), profile=ScanProfile.STANDARD, socks=("127.0.0.1", 1080)
    )
    assert "-Pn" in plan.argv
    assert "--unprivileged" in plan.argv


def test_a_tunnelled_scan_is_actually_routed_through_the_proxy(adapter, tmp_path, settings):
    """Recording the association without routing the traffic would make the
    reachability map a claim rather than evidence."""
    settings.ENGINE = {**settings.ENGINE, "LOG_DIR": str(tmp_path / "logs")}
    plan = adapter.plan(
        target=net("10.4.0.0/24"), profile=ScanProfile.QUICK, socks=("127.0.0.1", 1080)
    )
    assert plan.argv[0].endswith("proxychains4")
    config_path = plan.argv[plan.argv.index("-f") + 1]
    assert "socks5 127.0.0.1 1080" in open(config_path).read()
    # nmap still comes after, with its own arguments intact.
    assert "/usr/bin/nmap" in plan.argv


def test_direct_scan_is_not_proxied(adapter):
    plan = adapter.plan(target=net("10.4.0.0/24"), profile=ScanProfile.STANDARD)
    assert not plan.argv[0].endswith("proxychains4")


def test_an_unprivileged_scan_skips_host_discovery(adapter, monkeypatch):
    """Without raw sockets nmap's discovery phase declares live hosts down.

    Found the hard way: a /24 sweep returned two services on one host in two
    seconds, because every other host had been skipped before a single port was
    tried.
    """
    monkeypatch.setattr(adapter, "has_raw_sockets", lambda: False)
    plan = adapter.plan(target=net("198.51.100.0/24"), profile=ScanProfile.QUICK)
    assert "-Pn" in plan.argv
    assert "--unprivileged" in plan.argv


def test_a_privileged_scan_lets_nmap_do_its_own_discovery(adapter, monkeypatch):
    monkeypatch.setattr(adapter, "has_raw_sockets", lambda: True)
    plan = adapter.plan(target=net("198.51.100.0/24"), profile=ScanProfile.QUICK)
    assert "-Pn" not in plan.argv


def test_ipv6_target_sets_the_ipv6_flag(adapter):
    plan = adapter.plan(target=net("2001:db8::/64"), profile=ScanProfile.QUICK)
    assert "-6" in plan.argv
    assert plan.argv[-1] == "2001:db8::/64"


def test_ipv4_target_does_not_set_the_ipv6_flag(adapter):
    plan = adapter.plan(target=net("10.4.0.0/24"), profile=ScanProfile.QUICK)
    assert "-6" not in plan.argv
