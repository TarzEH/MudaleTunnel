"""nmap adapter.

Two rules prevent command injection:
1. Operators choose a profile, never flags.  The profile→argv mapping is fixed.
2. The target is re-serialised from a parsed ipaddress object.

``--`` is placed before the target as a third layer.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

from mudale_engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from mudale_engine.enums import ScanProfile

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

XML_OUTPUT_ARGS: tuple[str, ...] = ("-oX", "-")

PROFILE_ARGS: dict[str, tuple[str, ...]] = {
    ScanProfile.DISCOVERY: ("-sn", "-T4"),
    ScanProfile.QUICK: ("-sT", "-F", "-T4", "--open"),
    ScanProfile.STANDARD: ("-sT", "-sV", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.FULL: ("-sT", "-sV", "-p-", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.UDP_TOP: ("-sU", "--top-ports", "100", "-T4", "--open"),
}

PRIVILEGED_PROFILES = frozenset({ScanProfile.UDP_TOP})
UNPRIVILEGED_ARGS: tuple[str, ...] = ("-Pn", "--unprivileged")
PROXYCHAINS_QUIET = "-q"


class NmapAdapter:
    kind_prefix = "nmap"

    def __init__(
        self,
        nmap_bin: str,
        proxychains_bin: str = "proxychains4",
        state_dir: str | Path | None = None,
    ):
        self._configured = nmap_bin
        self._resolved: str | None = None
        self._configured_proxychains = proxychains_bin
        self._proxychains: str | None = None
        self._state_dir = Path(state_dir) if state_dir else Path.home() / ".mudale"

    def is_available(self) -> bool:
        try:
            self.binary()
        except AdapterUnavailable:
            return False
        return True

    def binary(self) -> str:
        if self._resolved is None:
            self._resolved = resolve_binary(self._configured, name="nmap")
        return self._resolved

    def plan(
        self,
        *,
        target: IPNetwork,
        profile: str,
        socks: tuple[str, int] | None = None,
    ) -> LaunchPlan:
        if not isinstance(target, ipaddress.IPv4Network | ipaddress.IPv6Network):
            raise TypeError(
                f"nmap target must be a parsed ip_network, got {type(target).__name__}"
            )

        args = PROFILE_ARGS.get(profile)
        if args is None:
            raise ValueError(f"Unknown scan profile {profile!r}")

        argv = [self.binary(), *args, *XML_OUTPUT_ARGS]
        if socks is not None or not self.has_raw_sockets():
            argv += list(UNPRIVILEGED_ARGS)
        if target.version == 6:
            argv.append("-6")
        argv += ["--", str(target)]

        cleanup: list[str] = []
        if socks is not None:
            config_path = self._write_proxychains_config(*socks)
            argv = [self.proxychains_binary(), PROXYCHAINS_QUIET, "-f", config_path, *argv]
            cleanup.append(config_path)

        return LaunchPlan(
            argv=argv,
            description=(
                f"{profile} scan of {target}"
                + (f" through {socks[0]}:{socks[1]}" if socks else "")
            ),
            startup_timeout=30.0,
            cleanup_files=cleanup,
        )

    @staticmethod
    def has_raw_sockets() -> bool:
        return os.geteuid() == 0

    def proxychains_binary(self) -> str:
        if self._proxychains is None:
            self._proxychains = resolve_binary(self._configured_proxychains, name="proxychains4")
        return self._proxychains

    def can_scan_through_a_pivot(self) -> bool:
        try:
            self.proxychains_binary()
        except AdapterUnavailable:
            return False
        return True

    def _write_proxychains_config(self, host: str, port: int) -> str:
        directory = self._state_dir / "proxychains"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / f"socks-{host.replace(':', '_')}-{port}.conf"
        path.write_text(
            "\n".join([
                "strict_chain",
                "proxy_dns",
                "remote_dns_subnet 224",
                "tcp_read_time_out 15000",
                "tcp_connect_time_out 8000",
                "[ProxyList]",
                f"socks5 {host} {port}",
                "",
            ])
        )
        path.chmod(0o600)
        return str(path)

    @staticmethod
    def requires_root(profile: str) -> bool:
        return profile in PRIVILEGED_PROFILES

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        detail = (stderr or "").strip().splitlines()
        last_line = detail[-1] if detail else ""
        if returncode == 0:
            return "Scan completed"
        if returncode < 0:
            return f"Scan was terminated by signal {-returncode}"
        base = f"nmap exited with code {returncode}"
        return f"{base}: {last_line}" if last_line else base
