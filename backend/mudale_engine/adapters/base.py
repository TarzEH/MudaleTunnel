"""Adapter protocol.

An adapter turns a validated spec into something the supervisor can run and
watch.  Adapters are pure with respect to the database: they build argv lists
and interpret exit codes, and the supervisor owns process lifecycle and model
updates.
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
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    startup_timeout: float = 15.0
    cleanup_files: list[str] = field(default_factory=list)


class TunnelAdapter(Protocol):
    kind_prefix: str

    def is_available(self) -> bool: ...
    def plan(self, spec, *, tunnel=None) -> LaunchPlan: ...
    def interpret_exit(self, returncode: int, stderr: str) -> str: ...


def resolve_binary(configured: str, *, name: str) -> str:
    """Resolve a configured binary to an absolute path."""
    if not configured:
        raise AdapterUnavailable(f"No {name} binary configured")
    resolved = shutil.which(configured)
    if resolved is None:
        raise AdapterUnavailable(f"{name} binary {configured!r} not found on PATH")
    return resolved
