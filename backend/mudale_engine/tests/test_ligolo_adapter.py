"""Tests for the ligolo-ng adapter's argv construction."""

from __future__ import annotations

import pytest

from mudale_engine.adapters.ligolo import LigoloAdapter
from mudale_engine.specs import LigoloSpec


@pytest.fixture
def adapter(monkeypatch):
    instance = LigoloAdapter("ligolo-proxy")
    monkeypatch.setattr(instance, "binary", lambda: "/usr/local/bin/ligolo-proxy")
    return instance


def spec(**overrides) -> LigoloSpec:
    defaults = {
        "agent_addr": "10.4.0.10",
        "listen_port": 11601,
        "tun_name": "ligolo",
        "laddr": "0.0.0.0",
        "selfcert": True,
    }
    return LigoloSpec(**{**defaults, **overrides})


def test_basic_argv(adapter):
    plan = adapter.plan(spec())
    assert plan.argv[0] == "/usr/local/bin/ligolo-proxy"
    assert "-laddr" in plan.argv
    assert plan.argv[plan.argv.index("-laddr") + 1] == "0.0.0.0:11601"
    assert "-tunname" in plan.argv
    assert plan.argv[plan.argv.index("-tunname") + 1] == "ligolo"
    assert "-selfcert" in plan.argv


def test_selfcert_disabled(adapter):
    plan = adapter.plan(spec(selfcert=False))
    assert "-selfcert" not in plan.argv


def test_custom_tun_name(adapter):
    plan = adapter.plan(spec(tun_name="pivot0"))
    assert plan.argv[plan.argv.index("-tunname") + 1] == "pivot0"


def test_custom_listen_port(adapter):
    plan = adapter.plan(spec(listen_port=9999))
    assert plan.argv[plan.argv.index("-laddr") + 1] == "0.0.0.0:9999"


def test_describe(adapter):
    desc = LigoloAdapter.describe(spec())
    assert "ligolo-ng" in desc
    assert "11601" in desc
    assert "10.4.0.10" in desc


def test_exit_0(adapter):
    assert "cleanly" in adapter.interpret_exit(0, "")


def test_exit_signal(adapter):
    assert "signal 15" in adapter.interpret_exit(-15, "")


def test_exit_error(adapter):
    msg = adapter.interpret_exit(1, "bind: address already in use")
    assert "address already in use" in msg


# ── Spec validation ───────────────────────────────────────────────────


def test_invalid_tun_name_rejected():
    with pytest.raises(Exception, match="not a valid TUN name"):
        LigoloSpec(
            agent_addr="10.4.0.10",
            tun_name="INVALID NAME!",
        )


def test_flag_shaped_agent_rejected():
    with pytest.raises(Exception, match="may not start with"):
        LigoloSpec(agent_addr="-evil")


def test_scope_id_in_agent_rejected():
    with pytest.raises(Exception, match="must not contain"):
        LigoloSpec(agent_addr="fe80::1%eth0")


def test_unknown_field_rejected():
    with pytest.raises(Exception):
        LigoloSpec(agent_addr="10.4.0.10", rogue_field="pwned")
