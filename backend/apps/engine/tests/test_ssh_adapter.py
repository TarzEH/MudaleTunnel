"""Tests for the SSH adapter's argv construction.

The first two tests are regression tests for the v2 defects described in
``apps.engine.adapters.ssh``. They are the reason the tunnel PID can be trusted.
"""

from __future__ import annotations

import pytest

from apps.engine.adapters.ssh import SshAdapter
from apps.engine.specs import (
    SshDynamicForwardSpec,
    SshEndpoint,
    SshLocalForwardSpec,
    SshRemoteDynamicSpec,
    SshRemoteForwardSpec,
)

ENDPOINT = SshEndpoint(user="opsec", host="10.4.0.10", port=2222)


@pytest.fixture
def adapter(monkeypatch):
    """An adapter with a stubbed binary path, so tests never need ssh installed."""
    instance = SshAdapter("ssh")
    monkeypatch.setattr(instance, "binary", lambda: "/usr/bin/ssh")
    return instance


def argv_for(adapter, spec) -> list[str]:
    return adapter.plan(spec).argv


# ── Regression: the v2 process-lifecycle bug ────────────────────────────


def test_argv_never_contains_the_background_flag(adapter):
    """``-f`` makes ssh fork and the tracked PID die. It must never be emitted.

    v2 used it on every tunnel, which is why stopping a tunnel raised
    ProcessLookupError and left it running.
    """
    specs = [
        SshLocalForwardSpec(
            endpoint=ENDPOINT, local_port=8080, target_host="10.4.9.5", target_port=443
        ),
        SshDynamicForwardSpec(endpoint=ENDPOINT, local_port=1080),
        SshRemoteForwardSpec(
            endpoint=ENDPOINT, remote_port=9000, target_host="127.0.0.1", target_port=8000
        ),
        SshRemoteDynamicSpec(endpoint=ENDPOINT, remote_port=1080),
    ]
    for spec in specs:
        argv = argv_for(adapter, spec)
        assert "-f" not in argv, f"{type(spec).__name__} emitted a backgrounding flag"
        assert "-N" in argv


def test_forward_failure_is_fatal(adapter):
    """Without ExitOnForwardFailure, "process alive" would not mean "tunnel up"."""
    argv = argv_for(adapter, SshDynamicForwardSpec(endpoint=ENDPOINT, local_port=1080))
    assert "ExitOnForwardFailure=yes" in argv


def test_never_prompts(adapter):
    """A prompt on a tty-less daemon hangs forever and looks like a dead tunnel."""
    argv = argv_for(adapter, SshDynamicForwardSpec(endpoint=ENDPOINT, local_port=1080))
    assert "BatchMode=yes" in argv

    plan = adapter.plan(SshDynamicForwardSpec(endpoint=ENDPOINT, local_port=1080))
    assert plan.env["SSH_ASKPASS_REQUIRE"] == "never"


def test_inherited_ssh_config_forwards_are_cleared(adapter):
    """The control plane's model of a tunnel has to be the whole truth."""
    argv = argv_for(adapter, SshDynamicForwardSpec(endpoint=ENDPOINT, local_port=1080))
    assert "ClearAllForwardings=yes" in argv


# ── Forward specifications ──────────────────────────────────────────────


def test_local_forward_argv(adapter):
    spec = SshLocalForwardSpec(
        endpoint=ENDPOINT, local_bind="127.0.0.1", local_port=8080,
        target_host="10.4.9.5", target_port=443,
    )
    argv = argv_for(adapter, spec)
    assert argv[0] == "/usr/bin/ssh"
    assert "-L" in argv
    assert argv[argv.index("-L") + 1] == "127.0.0.1:8080:10.4.9.5:443"
    assert argv[-1] == "opsec@10.4.0.10"
    assert argv[argv.index("-p") + 1] == "2222"


def test_dynamic_forward_argv(adapter):
    spec = SshDynamicForwardSpec(endpoint=ENDPOINT, local_bind="127.0.0.1", local_port=1080)
    argv = argv_for(adapter, spec)
    assert argv[argv.index("-D") + 1] == "127.0.0.1:1080"


def test_remote_forward_argv(adapter):
    spec = SshRemoteForwardSpec(
        endpoint=ENDPOINT, remote_bind="0.0.0.0", remote_port=9000,
        target_host="127.0.0.1", target_port=8000,
    )
    argv = argv_for(adapter, spec)
    assert argv[argv.index("-R") + 1] == "0.0.0.0:9000:127.0.0.1:8000"


def test_remote_dynamic_forward_argv(adapter):
    spec = SshRemoteDynamicSpec(endpoint=ENDPOINT, remote_bind="127.0.0.1", remote_port=1080)
    argv = argv_for(adapter, spec)
    assert argv[argv.index("-R") + 1] == "127.0.0.1:1080"


def test_identity_file_pins_the_key(adapter):
    """Without IdentitiesOnly, ssh also offers every agent key and the audit
    trail cannot say which one authenticated."""
    endpoint = SshEndpoint(user="opsec", host="10.4.0.10", identity_file="/keys/engagement.pem")
    argv = argv_for(adapter, SshDynamicForwardSpec(endpoint=endpoint, local_port=1080))
    assert argv[argv.index("-i") + 1] == "/keys/engagement.pem"
    assert "IdentitiesOnly=yes" in argv


def test_destination_is_the_final_argument(adapter):
    """ssh has no '--' separator, so the destination must be positionally last."""
    spec = SshLocalForwardSpec(
        endpoint=ENDPOINT, local_port=8080, target_host="10.4.9.5", target_port=443
    )
    assert argv_for(adapter, spec)[-1] == "opsec@10.4.0.10"


# ── Exit interpretation ─────────────────────────────────────────────────


def test_exit_255_is_explained(adapter):
    message = adapter.interpret_exit(255, "bind: Address already in use")
    assert "could not connect" in message
    assert "Address already in use" in message


def test_signal_exit_is_explained(adapter):
    assert "signal 15" in adapter.interpret_exit(-15, "")


def test_clean_exit_is_explained(adapter):
    assert adapter.interpret_exit(0, "") == "SSH exited cleanly"
