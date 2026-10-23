"""Module registry — the use/set/run system (msfconsole-style).

Each module has a type (tunnel, scan, pivot), a name, options with defaults
and validation, and a run() method that executes via the engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mudale_engine.enums import ScanProfile, TunnelKind


@dataclass
class ModuleOption:
    name: str
    description: str
    required: bool = False
    default: Any = None
    choices: list[str] | None = None
    value_type: str = "str"


@dataclass
class Module:
    type: str
    name: str
    full_name: str
    description: str
    options: list[ModuleOption] = field(default_factory=list)
    _values: dict[str, Any] = field(default_factory=dict)

    def set_option(self, name: str, value: str) -> str | None:
        """Set an option value. Returns error string or None on success."""
        opt = self._find_option(name)
        if opt is None:
            return f"Unknown option: {name}"

        if opt.choices and value not in opt.choices:
            return f"Invalid value for {name}. Choices: {', '.join(opt.choices)}"

        if opt.value_type == "int":
            try:
                self._values[name] = int(value)
            except ValueError:
                return f"{name} must be an integer"
        elif opt.value_type == "bool":
            self._values[name] = value.lower() in ("true", "yes", "1")
        else:
            self._values[name] = value
        return None

    def unset_option(self, name: str) -> str | None:
        opt = self._find_option(name)
        if opt is None:
            return f"Unknown option: {name}"
        self._values.pop(name, None)
        return None

    def get_option(self, name: str) -> Any:
        opt = self._find_option(name)
        if opt is None:
            return None
        return self._values.get(name, opt.default)

    def validate(self) -> list[str]:
        """Check all required options are set. Returns list of errors."""
        errors = []
        for opt in self.options:
            val = self._values.get(opt.name, opt.default)
            if opt.required and (val is None or val == ""):
                errors.append(f"Required option not set: {opt.name}")
        return errors

    def get_options_table(self) -> list[dict]:
        rows = []
        for opt in self.options:
            val = self._values.get(opt.name, opt.default)
            rows.append({
                "name": opt.name,
                "current": str(val) if val is not None else "",
                "required": "yes" if opt.required else "no",
                "description": opt.description,
            })
        return rows

    def _find_option(self, name: str) -> ModuleOption | None:
        name_upper = name.upper()
        for opt in self.options:
            if opt.name.upper() == name_upper:
                return opt
        return None


# ── Module definitions ─────────────────────────────────────────────────

_SSH_ENDPOINT_OPTIONS = [
    ModuleOption("RHOST", "Target SSH host", required=True),
    ModuleOption("RPORT", "Target SSH port", default="22", value_type="int"),
    ModuleOption("USERNAME", "SSH username", required=True, default="root"),
    ModuleOption("IDENTITY", "Path to SSH private key"),
    ModuleOption("STRICT_HOST_KEY", "Verify host key", default="false", value_type="bool"),
]


def _create_ssh_local() -> Module:
    return Module(
        type="tunnel",
        name="ssh_local",
        full_name="tunnel/ssh_local",
        description="SSH local port forward (-L) — reach a remote service locally",
        options=[
            *_SSH_ENDPOINT_OPTIONS,
            ModuleOption("LHOST", "Local bind address", default="127.0.0.1"),
            ModuleOption("LPORT", "Local listen port", required=True, value_type="int"),
            ModuleOption("TARGET_HOST", "Remote target host", required=True),
            ModuleOption("TARGET_PORT", "Remote target port", required=True, value_type="int"),
        ],
    )


def _create_ssh_dynamic() -> Module:
    return Module(
        type="tunnel",
        name="ssh_dynamic",
        full_name="tunnel/ssh_dynamic",
        description="SSH SOCKS proxy (-D) — route traffic through a remote host",
        options=[
            *_SSH_ENDPOINT_OPTIONS,
            ModuleOption("LHOST", "Local bind address", default="127.0.0.1"),
            ModuleOption(
                "LPORT", "Local SOCKS port",
                required=True, default="1080", value_type="int",
            ),
        ],
    )


def _create_ssh_remote() -> Module:
    return Module(
        type="tunnel",
        name="ssh_remote",
        full_name="tunnel/ssh_remote",
        description="SSH reverse forward (-R) — expose a local service on the remote host",
        options=[
            *_SSH_ENDPOINT_OPTIONS,
            ModuleOption("REMOTE_BIND", "Remote bind address", default="127.0.0.1"),
            ModuleOption("REMOTE_PORT", "Remote listen port", required=True, value_type="int"),
            ModuleOption("TARGET_HOST", "Local target host", required=True, default="127.0.0.1"),
            ModuleOption("TARGET_PORT", "Local target port", required=True, value_type="int"),
        ],
    )


def _create_ssh_remote_dynamic() -> Module:
    return Module(
        type="tunnel",
        name="ssh_remote_dynamic",
        full_name="tunnel/ssh_remote_dynamic",
        description="SSH reverse SOCKS (-R) — create a SOCKS proxy on the remote host",
        options=[
            *_SSH_ENDPOINT_OPTIONS,
            ModuleOption("REMOTE_BIND", "Remote bind address", default="127.0.0.1"),
            ModuleOption("REMOTE_PORT", "Remote SOCKS port", required=True, value_type="int"),
        ],
    )


def _create_nmap_scan() -> Module:
    profiles = [p.value for p in ScanProfile]
    return Module(
        type="scan",
        name="nmap",
        full_name="scan/nmap",
        description="nmap network scan — discover hosts and services",
        options=[
            ModuleOption("TARGET", "Target IP/CIDR", required=True),
            ModuleOption(
                "PROFILE", "Scan profile", required=True,
                default="standard", choices=profiles,
            ),
            ModuleOption("VIA_TUNNEL", "Route scan through tunnel ID", value_type="int"),
        ],
    )


def _create_ligolo() -> Module:
    return Module(
        type="tunnel",
        name="ligolo",
        full_name="tunnel/ligolo",
        description="ligolo-ng TUN tunnel — full IP-layer pivoting (TCP/UDP/ICMP)",
        options=[
            ModuleOption(
                "AGENT_ADDR", "Agent callback address (where the agent connects from)",
                required=True,
            ),
            ModuleOption("LISTEN_PORT", "Proxy listen port", default="11601", value_type="int"),
            ModuleOption("TUN_NAME", "TUN interface name", default="ligolo"),
            ModuleOption("LADDR", "Proxy listen address", default="0.0.0.0"),  # noqa: S104
            ModuleOption(
                "SELFCERT", "Use self-signed certificate",
                default="true", value_type="bool",
            ),
        ],
    )


def _create_pivot_auto() -> Module:
    return Module(
        type="pivot",
        name="auto",
        full_name="pivot/auto",
        description="Auto-pivot — scan through a SOCKS tunnel and expose found services",
        options=[
            ModuleOption(
                "TUNNEL_ID", "SOCKS tunnel to pivot through",
                required=True, value_type="int",
            ),
            ModuleOption("TARGET", "Target subnet to discover", required=True),
            ModuleOption("PROFILE", "Scan profile", default="quick",
                         choices=[p.value for p in ScanProfile]),
        ],
    )


MODULE_REGISTRY: dict[str, callable] = {
    "tunnel/ssh_local": _create_ssh_local,
    "tunnel/ssh_dynamic": _create_ssh_dynamic,
    "tunnel/ssh_remote": _create_ssh_remote,
    "tunnel/ssh_remote_dynamic": _create_ssh_remote_dynamic,
    "tunnel/ligolo": _create_ligolo,
    "scan/nmap": _create_nmap_scan,
    "pivot/auto": _create_pivot_auto,
}


def get_module(name: str) -> Module | None:
    factory = MODULE_REGISTRY.get(name)
    if factory is None:
        return None
    return factory()


def list_modules() -> list[dict]:
    result = []
    for _name, factory in MODULE_REGISTRY.items():
        mod = factory()
        result.append({
            "name": mod.full_name,
            "type": mod.type,
            "description": mod.description,
        })
    return result


def build_tunnel_spec(module: Module) -> tuple[str, dict]:
    """Convert module options into a (kind, spec_dict) tuple for the engine."""
    endpoint = {
        "user": module.get_option("USERNAME"),
        "host": module.get_option("RHOST"),
        "port": module.get_option("RPORT") or 22,
        "strict_host_key_checking": module.get_option("STRICT_HOST_KEY") or False,
    }
    identity = module.get_option("IDENTITY")
    if identity:
        endpoint["identity_file"] = identity

    if module.name == "ssh_local":
        return TunnelKind.SSH_LOCAL, {
            "endpoint": endpoint,
            "local_bind": module.get_option("LHOST") or "127.0.0.1",
            "local_port": module.get_option("LPORT"),
            "target_host": module.get_option("TARGET_HOST"),
            "target_port": module.get_option("TARGET_PORT"),
        }
    elif module.name == "ssh_dynamic":
        return TunnelKind.SSH_DYNAMIC, {
            "endpoint": endpoint,
            "local_bind": module.get_option("LHOST") or "127.0.0.1",
            "local_port": module.get_option("LPORT"),
        }
    elif module.name == "ssh_remote":
        return TunnelKind.SSH_REMOTE, {
            "endpoint": endpoint,
            "remote_bind": module.get_option("REMOTE_BIND") or "127.0.0.1",
            "remote_port": module.get_option("REMOTE_PORT"),
            "target_host": module.get_option("TARGET_HOST"),
            "target_port": module.get_option("TARGET_PORT"),
        }
    elif module.name == "ssh_remote_dynamic":
        return TunnelKind.SSH_REMOTE_DYNAMIC, {
            "endpoint": endpoint,
            "remote_bind": module.get_option("REMOTE_BIND") or "127.0.0.1",
            "remote_port": module.get_option("REMOTE_PORT"),
        }
    elif module.name == "ligolo":
        return TunnelKind.LIGOLO, {
            "agent_addr": module.get_option("AGENT_ADDR"),
            "listen_port": module.get_option("LISTEN_PORT") or 11601,
            "tun_name": module.get_option("TUN_NAME") or "ligolo",
            "laddr": module.get_option("LADDR") or "0.0.0.0",  # noqa: S104
            "selfcert": (
                module.get_option("SELFCERT")
                if module.get_option("SELFCERT") is not None
                else True
            ),
        }
    raise ValueError(f"Unknown tunnel module: {module.name}")
