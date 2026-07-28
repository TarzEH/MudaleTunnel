"""Adapter protocol.

An adapter turns a validated spec into something the supervisor can run and
watch. Adapters are pure with respect to the database: they build argv lists and
interpret exit codes, and the supervisor owns process lifecycle and model
updates. That split is what makes them testable without spawning anything.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from typing import Protocol


class AdapterUnavailable(RuntimeError):
    """The adapter's binary is missing, so it cannot be used."""


@dataclass(frozen=True)
class LaunchPlan:
    """Everything needed to start and supervise one process."""

    argv: list[str]
    #: Extra environment for the child, merged over a scrubbed base environment.
    env: dict[str, str] = field(default_factory=dict)
    #: Human-readable one-liner for the dashboard and audit log. Safe to show —
    #: it is derived from the same validated fields as the argv.
    description: str = ""
    #: Seconds to allow between spawn and "this should be working by now".
    startup_timeout: float = 15.0


class TunnelAdapter(Protocol):
    """Builds launch plans for one family of tunnels."""

    kind_prefix: str

    def is_available(self) -> bool: ...

    def plan(self, spec, *, tunnel) -> LaunchPlan: ...

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        """Turn a process exit into an operator-readable explanation."""
        ...


def resolve_binary(configured: str, *, name: str) -> str:
    """Resolve a configured binary to an absolute path.

    Raises :class:`AdapterUnavailable` rather than returning a bare name, so a
    missing binary is reported at startup as a disabled capability instead of
    surfacing later as a confusing ENOENT on the first tunnel.
    """
    if not configured:
        raise AdapterUnavailable(f"No {name} binary configured")
    resolved = shutil.which(configured)
    if resolved is None:
        raise AdapterUnavailable(f"{name} binary {configured!r} not found on PATH")
    return resolved
