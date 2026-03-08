"""
Shared nmap output parser.
Used by both CLI (MudaleTunnelUI) and web interface (web_app).
"""
from typing import Dict, List


def parse_nmap_services(output: str) -> List[Dict[str, str]]:
    """
    Parse nmap output and extract open services.

    Returns list of dicts with keys: port, state, service
    Example: [{"port": "22/tcp", "state": "open", "service": "ssh"}]
    """
    services = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Match nmap port output: "22/tcp open ssh" or "80/tcp open http Apache 2.4"
        if ("/tcp" not in line and "/udp" not in line) or "open" not in line:
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        # Find the index of "open"
        open_idx = next((i for i, p in enumerate(parts) if p == "open"), None)
        if open_idx is None or open_idx == 0:
            continue

        port = parts[0]
        state = parts[open_idx]
        service = parts[open_idx + 1] if open_idx + 1 < len(parts) else "unknown"

        # Skip non-service states that may appear after "open"
        if service in ("filtered", "closed", "unfiltered"):
            continue

        services.append({
            "port": port,
            "state": state,
            "service": service,
        })

    return services
