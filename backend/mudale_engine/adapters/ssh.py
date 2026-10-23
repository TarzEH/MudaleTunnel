"""SSH tunnel adapter.

No ``-f``: ssh stays in the foreground so the supervisor tracks the real PID.
``ExitOnForwardFailure=yes``: a failed forward is a process exit, not a silent nothing.
``-F /dev/null``: the user's ssh_config cannot redirect a tunnel.
"""

from __future__ import annotations

from pathlib import Path

from mudale_engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from mudale_engine.specs import (
    SshDynamicForwardSpec,
    SshEndpoint,
    SshLocalForwardSpec,
    SshRemoteDynamicSpec,
    SshRemoteForwardSpec,
)

BASE_SSH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("BatchMode", "yes"),
    ("ExitOnForwardFailure", "yes"),
    ("ServerAliveInterval", "10"),
    ("ServerAliveCountMax", "3"),
    ("ConnectTimeout", "10"),
    ("RequestTTY", "no"),
    ("PermitLocalCommand", "no"),
)

EXIT_EXPLANATIONS: dict[int, str] = {
    255: "SSH could not connect or authenticate, or a forward could not be bound",
}


class SshAdapter:
    kind_prefix = "ssh"

    def __init__(self, ssh_bin: str, state_dir: str | Path | None = None):
        self._configured = ssh_bin
        self._resolved: str | None = None
        self._state_dir = Path(state_dir) if state_dir else Path.home() / ".mudale"

    def known_hosts_path(self) -> str:
        directory = self._state_dir
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return str(directory / "known_hosts")

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

    @staticmethod
    def describe(spec) -> str:
        if isinstance(spec, SshLocalForwardSpec):
            return (
                f"{spec.local_bind}:{spec.local_port} → "
                f"{spec.target_host}:{spec.target_port} via {spec.endpoint.host}"
            )
        if isinstance(spec, SshDynamicForwardSpec):
            return f"SOCKS on {spec.local_bind}:{spec.local_port} via {spec.endpoint.host}"
        if isinstance(spec, SshRemoteForwardSpec):
            return (
                f"{spec.endpoint.host}:{spec.remote_bind}:{spec.remote_port} → "
                f"{spec.target_host}:{spec.target_port}"
            )
        if isinstance(spec, SshRemoteDynamicSpec):
            return (
                f"Reverse SOCKS on {spec.endpoint.host}:{spec.remote_bind}:{spec.remote_port}"
            )
        raise TypeError(f"SshAdapter cannot describe {type(spec).__name__}")

    def plan(self, spec, *, tunnel=None) -> LaunchPlan:
        description = self.describe(spec)

        if isinstance(spec, SshLocalForwardSpec):
            forward = [
                "-L",
                f"{spec.local_bind}:{spec.local_port}:{spec.target_host}:{spec.target_port}",
            ]
        elif isinstance(spec, SshDynamicForwardSpec):
            forward = ["-D", f"{spec.local_bind}:{spec.local_port}"]
        elif isinstance(spec, SshRemoteForwardSpec):
            forward = [
                "-R",
                f"{spec.remote_bind}:{spec.remote_port}:{spec.target_host}:{spec.target_port}",
            ]
        elif isinstance(spec, SshRemoteDynamicSpec):
            forward = ["-R", f"{spec.remote_bind}:{spec.remote_port}"]
        else:
            raise TypeError(f"SshAdapter cannot plan {type(spec).__name__}")

        argv = [
            self.binary(),
            *self._common_args(spec.endpoint),
            *forward,
            # FIX H2: use -l user instead of user@host to avoid
            # scope-ID smuggling through the @ separator.
            "-l", spec.endpoint.user,
            spec.endpoint.host,
        ]

        return LaunchPlan(
            argv=argv,
            env=self._child_env(),
            description=description,
            startup_timeout=20.0,
        )

    def _common_args(self, endpoint: SshEndpoint) -> list[str]:
        args: list[str] = [
            "-N", "-T",
            "-F", "/dev/null",
            "-o", f"UserKnownHostsFile={self.known_hosts_path()}",
            "-p", str(endpoint.port),
        ]

        for name, value in BASE_SSH_OPTIONS:
            args += ["-o", f"{name}={value}"]

        args += [
            "-o",
            f"StrictHostKeyChecking={'yes' if endpoint.strict_host_key_checking else 'accept-new'}",
        ]

        if endpoint.identity_file:
            args += ["-i", endpoint.identity_file, "-o", "IdentitiesOnly=yes"]

        return args

    @staticmethod
    def _child_env() -> dict[str, str]:
        return {"SSH_ASKPASS_REQUIRE": "never", "DISPLAY": ""}

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        detail = (stderr or "").strip().splitlines()
        last_line = detail[-1] if detail else ""
        if returncode == 0:
            return "SSH exited cleanly"
        if returncode < 0:
            return f"SSH was terminated by signal {-returncode}"
        base = EXIT_EXPLANATIONS.get(returncode, f"SSH exited with code {returncode}")
        return f"{base}: {last_line}" if last_line else base
