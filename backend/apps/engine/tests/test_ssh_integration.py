"""Integration test: a tunnel must actually carry traffic.

This exists because the unit tests did not catch a real bug. They asserted that
certain ssh options were *present* in the argv, which is not the same as
asserting the tunnel *works*: ``ClearAllForwardings=yes`` was being emitted, and
it clears the very forwarding the adapter had just requested. ssh authenticated,
stayed connected, listened on nothing, and reported healthy.

So this test starts a real user-mode ``sshd``, brings a real SOCKS tunnel up
through the supervisor, and pushes a real TCP connection through it. It skips
itself when the environment cannot support that, rather than failing.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from apps.engine.adapters.ssh import SshAdapter
from apps.engine.process import SupervisedProcess
from apps.engine.specs import SshDynamicForwardSpec, SshEndpoint

SSHD = "/usr/sbin/sshd"
pytestmark = pytest.mark.skipif(
    not Path(SSHD).exists() or shutil.which("ssh") is None,
    reason="needs a local sshd and ssh client",
)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_listener(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.1)
    return False


@pytest.fixture
def sshd(tmp_path):
    """A throwaway sshd on a high port, key-auth only, in a temp directory."""
    import getpass

    port = free_port()
    host_key = tmp_path / "hostkey"
    client_key = tmp_path / "clientkey"

    for target in (host_key, client_key):
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-f", str(target), "-N", ""],
            check=True,
            capture_output=True,
        )

    (tmp_path / "authorized_keys").write_bytes((tmp_path / "clientkey.pub").read_bytes())
    for path in (host_key, client_key, tmp_path / "authorized_keys"):
        path.chmod(0o600)

    config = tmp_path / "sshd_config"
    config.write_text(
        "\n".join(
            [
                f"Port {port}",
                "ListenAddress 127.0.0.1",
                f"HostKey {host_key}",
                f"AuthorizedKeysFile {tmp_path / 'authorized_keys'}",
                "PasswordAuthentication no",
                "UsePAM no",
                "PubkeyAuthentication yes",
                "StrictModes no",
                "AllowTcpForwarding yes",
            ]
        )
    )

    process = subprocess.Popen(
        [SSHD, "-f", str(config), "-D", "-e"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )

    if not wait_for_listener(port, timeout=5.0):
        process.terminate()
        pytest.skip("could not start a user-mode sshd in this environment")

    yield {"port": port, "key": str(client_key), "user": getpass.getuser()}

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        process.kill()


def test_socks_tunnel_actually_carries_traffic(sshd):
    """The regression test for ClearAllForwardings.

    Asserts behaviour, not argv contents: something must be listening on the
    SOCKS port, and a SOCKS5 handshake through it must succeed.
    """
    socks_port = free_port()
    spec = SshDynamicForwardSpec(
        endpoint=SshEndpoint(
            user=sshd["user"],
            host="127.0.0.1",
            port=sshd["port"],
            identity_file=sshd["key"],
            strict_host_key_checking=False,
        ),
        local_bind="127.0.0.1",
        local_port=socks_port,
    )

    plan = SshAdapter("ssh").plan(spec)
    process = SupervisedProcess(argv=plan.argv, env=plan.env, description=plan.description)
    pid = process.start()

    try:
        assert wait_for_listener(socks_port), (
            "nothing is listening on the SOCKS port — ssh connected but forwards nothing"
        )

        # A minimal SOCKS5 greeting: version 5, one method, "no authentication".
        # A working proxy answers 0x05 0x00.
        with socket.create_connection(("127.0.0.1", socks_port), timeout=5) as client:
            client.sendall(bytes([0x05, 0x01, 0x00]))
            reply = client.recv(2)
        assert reply == bytes([0x05, 0x00]), f"not a working SOCKS5 proxy: {reply!r}"

        assert process.poll() is None, "ssh exited while it was supposed to be tunnelling"
    finally:
        outcome = process.stop(grace_seconds=5)

    # And stopping must really stop it — v2 left unkillable tunnels behind.
    assert outcome.requested is True
    from apps.engine.process import is_pid_alive

    assert not is_pid_alive(pid)
    assert not wait_for_listener(socks_port, timeout=2.0), "the SOCKS port is still bound"
