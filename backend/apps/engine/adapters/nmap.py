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

from apps.engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from apps.scans.models import ScanProfile

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

#: Profile → nmap arguments. The single source of truth for what a scan may do.
#:
#: Deliberately excluded from every profile:
#:   -sS/-sU raw-socket scans   need root; the engine must not require it
#:   -O, -A                     OS detection needs raw sockets too
#:   --script                   arbitrary NSE execution
#:   -oN/-oX/-oG/--datadir      anything that writes to the filesystem
#: Output is captured from stdout instead, so nmap never writes a file.
PROFILE_ARGS: dict[str, tuple[str, ...]] = {
    ScanProfile.DISCOVERY: ("-sn", "-T4"),
    ScanProfile.QUICK: ("-sT", "-F", "-T4", "--open"),
    ScanProfile.STANDARD: ("-sT", "-sV", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.FULL: ("-sT", "-sV", "-p-", "--version-intensity", "2", "-T4", "--open"),
    ScanProfile.UDP_TOP: ("-sU", "--top-ports", "100", "-T4", "--open"),
}

#: Profiles whose nmap arguments require raw sockets, i.e. root on the engine host.
PRIVILEGED_PROFILES = frozenset({ScanProfile.UDP_TOP})

#: Appended when the scan is routed through a tunnel.
#:
#: Through a userland pivot there are no raw sockets, so a "SYN scan" silently
#: degrades to a connect() scan and nmap's own host discovery misreports hosts as
#: down. -Pn --unprivileged tells nmap the truth about its environment and stops
#: it drawing conclusions it cannot support.
TUNNELLED_ARGS: tuple[str, ...] = ("-Pn", "--unprivileged")


class NmapAdapter:
    kind_prefix = "nmap"

    def __init__(self, nmap_bin: str):
        self._configured = nmap_bin
        self._resolved: str | None = None

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
        through_tunnel: bool = False,
    ) -> LaunchPlan:
        """Build the launch plan for one scan.

        ``target`` must already be a parsed, scope-checked network object. The
        type annotation is enforced at runtime because this is the boundary the
        whole injection defence rests on.
        """
        if not isinstance(target, ipaddress.IPv4Network | ipaddress.IPv6Network):
            raise TypeError(
                f"nmap target must be a parsed ip_network, got {type(target).__name__}. "
                f"Parse and scope-check it with apps.engagements.scope first."
            )

        args = PROFILE_ARGS.get(profile)
        if args is None:
            raise ValueError(f"Unknown scan profile {profile!r}")

        argv = [self.binary(), *args]
        if through_tunnel:
            argv += list(TUNNELLED_ARGS)
        if target.version == 6:
            argv.append("-6")

        # Everything after '--' is a target, never an option.
        argv += ["--", str(target)]

        return LaunchPlan(
            argv=argv,
            description=f"{profile} scan of {target}",
            startup_timeout=30.0,
        )

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
