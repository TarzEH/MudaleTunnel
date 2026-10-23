"""ligolo-ng adapter.

ligolo-ng works differently from SSH tunnels: the *proxy* runs on the
operator's machine and listens for callbacks from a lightweight *agent*
that was deployed on the target.  When an agent connects, a TUN interface
is created and routes are added, so the operator's machine can reach the
remote network natively — no SOCKS proxy, no proxychains, every tool
works unmodified.

The trade-off against SSH tunnels is honest: ligolo needs an agent dropped
on the target and typically needs root on the operator's machine (to
create TUN interfaces and add routes).  What you get is full IP-layer
connectivity (TCP, UDP, ICMP), which SSH SOCKS cannot provide.
"""

from __future__ import annotations

from mudale_engine.adapters.base import AdapterUnavailable, LaunchPlan, resolve_binary
from mudale_engine.specs import LigoloSpec

EXIT_EXPLANATIONS: dict[int, str] = {
    1: "ligolo-ng proxy exited with a generic error",
}


class LigoloAdapter:
    kind_prefix = "ligolo"

    def __init__(self, ligolo_bin: str):
        self._configured = ligolo_bin
        self._resolved: str | None = None

    def is_available(self) -> bool:
        try:
            self.binary()
        except AdapterUnavailable:
            return False
        return True

    def binary(self) -> str:
        if self._resolved is None:
            self._resolved = resolve_binary(self._configured, name="ligolo-proxy")
        return self._resolved

    @staticmethod
    def describe(spec: LigoloSpec) -> str:
        return (
            f"ligolo-ng proxy listening on {spec.laddr}:{spec.listen_port} "
            f"(agent: {spec.agent_addr}, tun: {spec.tun_name})"
        )

    def plan(self, spec: LigoloSpec, *, tunnel=None) -> LaunchPlan:
        description = self.describe(spec)

        argv = [
            self.binary(),
            "-laddr", f"{spec.laddr}:{spec.listen_port}",
            "-tunname", spec.tun_name,
        ]

        if spec.selfcert:
            argv.append("-selfcert")

        return LaunchPlan(
            argv=argv,
            description=description,
            startup_timeout=10.0,
        )

    def interpret_exit(self, returncode: int, stderr: str) -> str:
        detail = (stderr or "").strip().splitlines()
        last_line = detail[-1] if detail else ""
        if returncode == 0:
            return "ligolo-ng proxy exited cleanly"
        if returncode < 0:
            return f"ligolo-ng proxy was terminated by signal {-returncode}"
        base = EXIT_EXPLANATIONS.get(returncode, f"ligolo-ng exited with code {returncode}")
        return f"{base}: {last_line}" if last_line else base
