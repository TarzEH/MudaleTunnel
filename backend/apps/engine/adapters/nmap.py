"""nmap adapter.

This is the file that closes v2's worst hole. There, ``ScanRequest.target`` was
appended verbatim to an argv from an unauthenticated endpoint, in a container
running as root — so ``-oN /etc/cron.d/x`` was a file write, and
``--script=...`` was code execution.

Two rules make that unreachable here:

1. **Operators choose a profile, never flags.** The mapping from profile name to
   nmap arguments lives in this module as a fixed table. No user input ever
   becomes an nmap option.
2. **The target is re-serialised from a parsed object.** The caller hands in an
   ``ipaddress`` network that has already been scope-checked; the argv is built
   from ``str(network)``, not from the operator's original string. A value that
   is not a network cannot survive the round trip.

``--`` is placed before the target as a third layer: even a hypothetical parser
bug that let a dash through would be read by nmap as a target, not an option.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

from apps.engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from apps.scans.models import ScanProfile

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: Emit XML on stdout. The '-' destination is ours, not user input, so nmap
#: still never writes a file — and structured output means results are parsed
#: from a real document instead of by pattern-matching human-readable text,
#: which is what made v2's parser miss services.
XML_OUTPUT_ARGS: tuple[str, ...] = ("-oX", "-")

#: Profile → nmap arguments. The single source of truth for what a scan may do.
#:
#: Deliberately excluded from every profile:
#:   -sS raw-socket SYN scan    needs root; the engine must not require it
#:   -O, -A                     OS detection needs raw sockets too
#:   --script                   arbitrary NSE execution
#:   -oN/-oG/-oA/--datadir      anything that writes to a path
#: The only output flag is XML_OUTPUT_ARGS above, which goes to stdout.
PROFILE_ARGS: dict[str, tuple[str, ...]] = {
    ScanProfile.DISCOVERY: ("-sn", "-T4"),
    ScanProfile.QUICK: ("-sT", "-F", "-T4", "--open"),
    ScanProfile.STANDARD: ("-sT", "-sV", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.FULL: ("-sT", "-sV", "-p-", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.UDP_TOP: ("-sU", "--top-ports", "100", "-T4", "--open"),
}

#: Profiles whose nmap arguments require raw sockets, i.e. root on the engine host.
PRIVILEGED_PROFILES = frozenset({ScanProfile.UDP_TOP})

#: Appended whenever nmap cannot do its own host discovery properly — which is
#: any time it lacks raw sockets, i.e. through a SOCKS pivot *or* simply running
#: unprivileged.
#:
#: This matters more than it sounds. Without raw sockets nmap cannot send ICMP
#: echo or ARP probes, so its discovery phase concludes that live hosts are down
#: and skips them entirely. The scan then completes quickly and reports almost
#: nothing, which is indistinguishable from "the network is empty". -Pn says
#: "assume the host is up and just try the ports"; --unprivileged stops nmap
#: attempting raw-socket techniques it will silently fail at.
UNPRIVILEGED_ARGS: tuple[str, ...] = ("-Pn", "--unprivileged")

#: Kept as an alias: through a pivot the same reasoning applies.
TUNNELLED_ARGS = UNPRIVILEGED_ARGS

#: proxychains config written per scan. `-q` keeps its banner out of the XML we
#: parse from stdout.
PROXYCHAINS_QUIET = "-q"


class NmapAdapter:
    kind_prefix = "nmap"

    def __init__(self, nmap_bin: str, proxychains_bin: str = "proxychains4"):
        self._configured = nmap_bin
        self._resolved: str | None = None
        self._configured_proxychains = proxychains_bin
        self._proxychains: str | None = None

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
        """Build the launch plan for one scan.

        ``target`` must already be a parsed, scope-checked network object. The
        type annotation is enforced at runtime because this is the boundary the
        whole injection defence rests on.

        ``socks`` is the ``(host, port)`` of a pivot's SOCKS proxy. When given,
        nmap is run under proxychains so the scan genuinely travels through the
        foothold. Recording the association without routing the traffic would
        make the resulting map a claim rather than evidence, which is the whole
        point of discovering reachability this way.
        """
        if not isinstance(target, ipaddress.IPv4Network | ipaddress.IPv6Network):
            raise TypeError(
                f"nmap target must be a parsed ip_network, got {type(target).__name__}. "
                f"Parse and scope-check it with apps.engagements.scope first."
            )

        args = PROFILE_ARGS.get(profile)
        if args is None:
            raise ValueError(f"Unknown scan profile {profile!r}")

        argv = [self.binary(), *args, *XML_OUTPUT_ARGS]
        if socks is not None or not self.has_raw_sockets():
            argv += list(UNPRIVILEGED_ARGS)
        if target.version == 6:
            argv.append("-6")

        # Everything after '--' is a target, never an option.
        argv += ["--", str(target)]

        config_path = None
        if socks is not None:
            config_path = self._write_proxychains_config(*socks)
            argv = [self.proxychains_binary(), PROXYCHAINS_QUIET, "-f", config_path, *argv]

        return LaunchPlan(
            argv=argv,
            description=(
                f"{profile} scan of {target}"
                + (f" through {socks[0]}:{socks[1]}" if socks else "")
            ),
            startup_timeout=30.0,
        )

    @staticmethod
    def has_raw_sockets() -> bool:
        """Whether nmap will be able to do real host discovery.

        Only root gets raw sockets. The engine runs unprivileged by design, so
        this is normally False — and the scan arguments have to reflect that
        rather than pretend otherwise.
        """
        return os.geteuid() == 0

    def proxychains_binary(self) -> str:
        if self._proxychains is None:
            self._proxychains = resolve_binary(self._configured_proxychains, name="proxychains4")
        return self._proxychains

    def can_scan_through_a_pivot(self) -> bool:
        """Whether tunnelled scans are possible on this host."""
        try:
            self.proxychains_binary()
        except AdapterUnavailable:
            return False
        return True

    def _write_proxychains_config(self, host: str, port: int) -> str:
        """Write a per-scan proxychains config.

        Written to a private directory under the engine's own state, not /tmp:
        a world-readable config naming a live pivot is an invitation.
        """
        from django.conf import settings

        directory = Path(settings.ENGINE["LOG_DIR"]).parent / "proxychains"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

        path = directory / f"socks-{host.replace(':', '_')}-{port}.conf"
        path.write_text(
            "\n".join(
                [
                    "strict_chain",
                    "proxy_dns",
                    "remote_dns_subnet 224",
                    "tcp_read_time_out 15000",
                    "tcp_connect_time_out 8000",
                    "[ProxyList]",
                    f"socks5 {host} {port}",
                    "",
                ]
            )
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
