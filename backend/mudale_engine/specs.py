"""Typed tunnel specifications.

A ``Tunnel.spec`` is JSON, which means it can be anything until something
validates it.  These models are that something: every adapter parses the stored
spec through the matching model before building an argv, so a field that reaches
a command line has been through type, range and character checks first.

The models are intentionally strict — unknown keys are an error rather than
being ignored, so a typo'd field cannot silently disable a constraint.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mudale_engine.enums import TunnelKind

logger = logging.getLogger(__name__)

Port = Annotated[int, Field(ge=1, le=65535)]

_SSH_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_.-]{0,31}$", re.IGNORECASE)

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


class SpecError(ValueError):
    """A stored spec does not satisfy its schema."""


class BaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _validate_host(value: str) -> str:
    """Accept an IP literal or a hostname; reject anything flag-shaped or smuggle-shaped."""
    if not value:
        raise ValueError("host cannot be empty")
    if value.startswith("-"):
        raise ValueError(f"host {value!r} may not start with '-'")
    # FIX H2: reject IPv6 scope IDs — the % character lets an attacker
    # smuggle a second @-separated host into the ssh destination.
    if "%" in value:
        raise ValueError(f"host {value!r} must not contain '%' (IPv6 scope IDs are not supported)")
    try:
        addr = ipaddress.ip_address(value)
        return str(addr)
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(value):
        raise ValueError(f"{value!r} is not a valid IP address or hostname")
    return value.lower()


def _validate_bind(value: str) -> str:
    """A bind address must be a literal IP — never a name."""
    if not value:
        raise ValueError("bind address cannot be empty")
    if "%" in value:
        raise ValueError(f"bind address {value!r} must not contain '%'")
    try:
        addr = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(
            f"bind address {value!r} must be a literal IP address "
            f"(127.0.0.1 for local-only, 0.0.0.0 to expose on every interface)"
        ) from exc
    if addr.is_unspecified:
        logger.warning(
            "Bind address %s exposes the forward on every interface — "
            "use 127.0.0.1 unless remote access is intended",
            value,
        )
    return str(addr)


class SshEndpoint(BaseSpec):
    """How to reach the SSH server that carries the tunnel."""

    user: str
    host: str
    port: Port = 22
    identity_file: str | None = None
    strict_host_key_checking: bool = True

    @field_validator("user")
    @classmethod
    def _check_user(cls, value: str) -> str:
        if not _SSH_USERNAME_RE.match(value):
            raise ValueError(
                f"{value!r} is not a valid SSH username (letters, digits, '.', '-', '_'; "
                f"must start with a letter or underscore)"
            )
        return value

    @field_validator("host")
    @classmethod
    def _check_host(cls, value: str) -> str:
        return _validate_host(value)

    @field_validator("identity_file")
    @classmethod
    def _check_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("/"):
            raise ValueError("identity_file must be an absolute path")
        if value.startswith("-"):
            raise ValueError("identity_file may not start with '-'")
        from pathlib import Path

        if ".." in Path(value).parts:
            raise ValueError("identity_file must not contain '..' components")
        resolved = Path(value).resolve()
        return str(resolved)


class SshLocalForwardSpec(BaseSpec):
    """``ssh -L local_port:target_host:target_port``"""

    kind: Literal[TunnelKind.SSH_LOCAL] = TunnelKind.SSH_LOCAL
    endpoint: SshEndpoint
    local_bind: str = "127.0.0.1"
    local_port: Port
    target_host: str
    target_port: Port

    @field_validator("local_bind")
    @classmethod
    def _check_bind(cls, value: str) -> str:
        return _validate_bind(value)

    @field_validator("target_host")
    @classmethod
    def _check_target(cls, value: str) -> str:
        return _validate_host(value)


class SshDynamicForwardSpec(BaseSpec):
    """``ssh -D local_port``"""

    kind: Literal[TunnelKind.SSH_DYNAMIC] = TunnelKind.SSH_DYNAMIC
    endpoint: SshEndpoint
    local_bind: str = "127.0.0.1"
    local_port: Port

    @field_validator("local_bind")
    @classmethod
    def _check_bind(cls, value: str) -> str:
        return _validate_bind(value)


class SshRemoteForwardSpec(BaseSpec):
    """``ssh -R bind:remote_port:target_host:target_port``"""

    kind: Literal[TunnelKind.SSH_REMOTE] = TunnelKind.SSH_REMOTE
    endpoint: SshEndpoint
    remote_bind: str = "127.0.0.1"
    remote_port: Port
    target_host: str
    target_port: Port

    @field_validator("remote_bind")
    @classmethod
    def _check_bind(cls, value: str) -> str:
        return _validate_bind(value)

    @field_validator("target_host")
    @classmethod
    def _check_target(cls, value: str) -> str:
        return _validate_host(value)


class SshRemoteDynamicSpec(BaseSpec):
    """``ssh -R bind:port`` — reverse SOCKS, needs OpenSSH 7.6+."""

    kind: Literal[TunnelKind.SSH_REMOTE_DYNAMIC] = TunnelKind.SSH_REMOTE_DYNAMIC
    endpoint: SshEndpoint
    remote_bind: str = "127.0.0.1"
    remote_port: Port

    @field_validator("remote_bind")
    @classmethod
    def _check_bind(cls, value: str) -> str:
        return _validate_bind(value)


# ── ligolo-ng ──────────────────────────────────────────────────────────


class LigoloSpec(BaseSpec):
    """ligolo-ng proxy — TUN-based pivoting without a SOCKS bottleneck.

    The proxy listens for agent callbacks. Once an agent connects, a TUN
    interface is created and routes are added so the operator's machine can
    reach the remote network natively — every tool works without proxychains.
    """

    kind: Literal[TunnelKind.LIGOLO] = TunnelKind.LIGOLO
    agent_addr: str
    listen_port: Port = 11601
    tun_name: str = "ligolo"
    selfcert: bool = True
    laddr: str = "0.0.0.0"  # noqa: S104

    @field_validator("agent_addr")
    @classmethod
    def _check_agent(cls, value: str) -> str:
        return _validate_host(value)

    @field_validator("laddr")
    @classmethod
    def _check_laddr(cls, value: str) -> str:
        return _validate_bind(value)

    @field_validator("tun_name")
    @classmethod
    def _check_tun(cls, value: str) -> str:
        if not re.match(r"^[a-z][a-z0-9_-]{0,14}$", value):
            raise ValueError(
                f"{value!r} is not a valid TUN name (lowercase letters, digits, "
                f"hyphens, underscores; max 15 chars)"
            )
        return value


AnyTunnelSpec = (
    SshLocalForwardSpec
    | SshDynamicForwardSpec
    | SshRemoteForwardSpec
    | SshRemoteDynamicSpec
    | LigoloSpec
)

SPEC_BY_KIND: dict[str, type[BaseSpec]] = {
    TunnelKind.SSH_LOCAL: SshLocalForwardSpec,
    TunnelKind.SSH_DYNAMIC: SshDynamicForwardSpec,
    TunnelKind.SSH_REMOTE: SshRemoteForwardSpec,
    TunnelKind.SSH_REMOTE_DYNAMIC: SshRemoteDynamicSpec,
    TunnelKind.LIGOLO: LigoloSpec,
}


def parse_spec(kind: str, raw: dict) -> BaseSpec:
    """Validate a raw spec dict against the schema for ``kind``."""
    model = SPEC_BY_KIND.get(kind)
    if model is None:
        raise SpecError(f"Unknown tunnel kind {kind!r}")
    try:
        return model.model_validate({**raw, "kind": kind})
    except Exception as exc:
        raise SpecError(f"Invalid {kind} spec: {exc}") from exc
