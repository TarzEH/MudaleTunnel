"""ASCII banner for the mudale console."""

from __future__ import annotations

BANNER = r"""
  ╔╦╗╦ ╦╔╦╗╔═╗╦  ╔═╗
  ║║║║ ║ ║║╠═╣║  ║╣
  ╩ ╩╚═╝═╩╝╩ ╩╩═╝╚═╝  {version}
   [ SSH tunnels • nmap scanning • network pivoting ]
"""

STATUS_LINE = (
    "   {modules} modules | {tunnels} active tunnels"
    " | {scans} running scans | engine: {engine}"
)


def render_banner(
    version: str = "4.0.0",
    module_count: int = 6,
    tunnel_count: int = 0,
    scan_count: int = 0,
    engine_status: str = "ready",
) -> str:
    banner = BANNER.format(version=f"v{version}")
    status = STATUS_LINE.format(
        modules=module_count,
        tunnels=tunnel_count,
        scans=scan_count,
        engine=engine_status,
    )
    return banner + status + "\n"
