"""SSH tunnel adapter.

Two decisions here are load-bearing, and both are corrections of v2 behaviour:

**No ``-f``.** ``ssh -f`` authenticates and then forks, with the *original*
process exiting. v2 stored that original PID, so as soon as anything called
``poll()`` the exited parent was reaped: the dashboard showed "stopped" while
traffic still flowed, and the later ``killpg`` raised ``ProcessLookupError`` and
left a live, unkillable tunnel into a client network. Keeping ssh in the
foreground under the supervisor means the tracked PID is the real process for
the tunnel's whole life, and stopping it actually stops it.

**``ExitOnForwardFailure=yes``.** Without it, ssh happily stays connected when a
forward could not be bound, so "process alive" stops implying "tunnel working"
and health has to be inferred by polling ports. With it, a failed forward is a
process exit, and liveness becomes a truthful health signal.
"""

from __future__ import annotations

from pathlib import Path

from apps.engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from apps.engine.specs import (
    SshDynamicForwardSpec,
    SshEndpoint,
    SshLocalForwardSpec,
    SshRemoteDynamicSpec,
    SshRemoteForwardSpec,
)

#: Options applied to every ssh invocation, in the order ssh will see them.
#:
#: BatchMode        — never prompt; the engine has no tty and a prompt would
#:                    hang indistinguishably from a dead tunnel.
#: ExitOnForwardFailure — see module docstring.
#: ServerAliveInterval/CountMax — notice a dead peer in ~30s instead of waiting
#:                    for TCP to time out, so the dashboard reflects reality.
#: ConnectTimeout   — bound how long a start attempt can hang.
#:
#: Note on what is deliberately *absent*: ``ClearAllForwardings=yes`` looks like
#: the right way to stop a user's ssh_config from adding forwardings we did not
#: ask for, but it clears the forwarding we *did* ask for too — ssh then connects
#: successfully and carries no traffic, with nothing for ExitOnForwardFailure to
#: catch. Isolation is achieved with ``-F /dev/null`` instead (see below), which
#: ignores the config file outright. Verified against a real sshd.
BASE_SSH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("BatchMode", "yes"),
    ("ExitOnForwardFailure", "yes"),
    ("ServerAliveInterval", "10"),
    ("ServerAliveCountMax", "3"),
    ("ConnectTimeout", "10"),
    # A tunnel process must never get a shell or a tty.
    ("RequestTTY", "no"),
    ("PermitLocalCommand", "no"),
)

EXIT_EXPLANATIONS: dict[int, str] = {
    255: "SSH could not connect or authenticate, or a forward could not be bound",
}


class SshAdapter:
    kind_prefix = "ssh"

    def __init__(self, ssh_bin: str, known_hosts: str | None = None):
        self._configured = ssh_bin
        self._resolved: str | None = None
        self._known_hosts = known_hosts

    def known_hosts_path(self) -> str:
        """Where the engine records host keys it has accepted."""
        if self._known_hosts:
            return self._known_hosts
        from django.conf import settings

        directory = Path(settings.ENGINE["LOG_DIR"]).parent
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory / "known_hosts")

    # ── Availability ────────────────────────────────────────────────────

    def is_available(self) -> bool:
        try:
            self.binary()
        except AdapterUnavailable:
            return False
        return True

    def binary(self) -> str:
        if self._resolved is None:
            self._resolved = resolve_binary(self._configured, name="ssh")
        return self._resolved

    # ── Planning ────────────────────────────────────────────────────────

    def plan(self, spec, *, tunnel=None) -> LaunchPlan:
        if isinstance(spec, SshLocalForwardSpec):
            forward = [
                "-L",
                f"{spec.local_bind}:{spec.local_port}:{spec.target_host}:{spec.target_port}",
            ]
            description = (
                f"{spec.local_bind}:{spec.local_port} → "
                f"{spec.target_host}:{spec.target_port} via {spec.endpoint.host}"
            )
        elif isinstance(spec, SshDynamicForwardSpec):
            forward = ["-D", f"{spec.local_bind}:{spec.local_port}"]
            description = f"SOCKS on {spec.local_bind}:{spec.local_port} via {spec.endpoint.host}"
        elif isinstance(spec, SshRemoteForwardSpec):
            forward = [
                "-R",
                f"{spec.remote_bind}:{spec.remote_port}:{spec.target_host}:{spec.target_port}",
            ]
            description = (
                f"{spec.endpoint.host}:{spec.remote_bind}:{spec.remote_port} → "
                f"{spec.target_host}:{spec.target_port}"
            )
        elif isinstance(spec, SshRemoteDynamicSpec):
            forward = ["-R", f"{spec.remote_bind}:{spec.remote_port}"]
            description = (
                f"Reverse SOCKS on {spec.endpoint.host}:{spec.remote_bind}:{spec.remote_port}"
            )
        else:
            raise TypeError(f"SshAdapter cannot plan {type(spec).__name__}")

        # Order matters: ssh's grammar is `ssh [options] destination [command]`,
        # so anything placed after the destination is sent to the remote host as
        # a command instead of being parsed as an option.
        argv = [
            self.binary(),
            *self._common_args(spec.endpoint),
            *forward,
            self._destination(spec.endpoint),
        ]

        return LaunchPlan(
            argv=argv,
            env=self._child_env(),
            description=description,
            startup_timeout=float(spec.endpoint.port and 20.0),
        )

    def _common_args(self, endpoint: SshEndpoint) -> list[str]:
        args: list[str] = [
            # -N: do not execute a remote command. -T: no pseudo-terminal.
            # Deliberately NOT -f: see module docstring.
            "-N",
            "-T",
            # Ignore the invoking user's ~/.ssh/config entirely. A tunnel's
            # behaviour must come from its stored spec and nothing else,
            # otherwise the control plane's model of what a tunnel does is
            # incomplete and a personal config could silently redirect a
            # tunnel into a client network.
            "-F",
            "/dev/null",
            # The control plane keeps its own host-key trust store rather than
            # borrowing the operator's ~/.ssh/known_hosts. Same reasoning as
            # -F /dev/null: a tunnel's behaviour must come from its spec, and a
            # key the operator happened to accept for an unrelated purpose is
            # not a decision this engine should inherit. Verification still
            # happens — it is just recorded against the engine's own file.
            "-o",
            f"UserKnownHostsFile={self.known_hosts_path()}",
            "-p",
            str(endpoint.port),
        ]

        for name, value in BASE_SSH_OPTIONS:
            args += ["-o", f"{name}={value}"]

        args += [
            "-o",
            f"StrictHostKeyChecking={'yes' if endpoint.strict_host_key_checking else 'accept-new'}",
        ]

        if endpoint.identity_file:
            # IdentitiesOnly stops ssh from also offering every key in the agent,
            # which would make "which key authenticated" unanswerable in the audit log.
            args += ["-i", endpoint.identity_file, "-o", "IdentitiesOnly=yes"]

        return args

    @staticmethod
    def _destination(endpoint: SshEndpoint) -> str:
        """The positional ``user@host`` argument.

        ssh has no ``--`` separator, so the destination's safety rests entirely
        on the schema: :class:`~apps.engine.specs.SshEndpoint` rejects usernames
        and hosts that start with ``-`` or contain whitespace, so this string
        cannot be re-read as an option.
        """
        return f"{endpoint.user}@{endpoint.host}"

    @staticmethod
    def _child_env() -> dict[str, str]:
        return {
            # Guarantees ssh fails instead of trying to pop a GUI passphrase prompt.
            "SSH_ASKPASS_REQUIRE": "never",
            "DISPLAY": "",
        }

    # ── Exit interpretation ─────────────────────────────────────────────

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        detail = (stderr or "").strip().splitlines()
        last_line = detail[-1] if detail else ""

        if returncode == 0:
            return "SSH exited cleanly"
        if returncode < 0:
            return f"SSH was terminated by signal {-returncode}"

        base = EXIT_EXPLANATIONS.get(returncode, f"SSH exited with code {returncode}")
        return f"{base}: {last_line}" if last_line else base
