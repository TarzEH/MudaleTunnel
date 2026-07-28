"""Helpers for pushing state changes to connected dashboards.

Called from the engine daemon (a synchronous process) and occasionally from the
web tier. Every function is fail-soft: if Redis is unreachable the operation
that triggered the broadcast must still succeed, because a missed UI update is
far less serious than a refused tunnel stop.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.api.consumers import engagement_group

logger = logging.getLogger(__name__)


def _send(engagement_id: int, payload: dict) -> None:
    try:
        layer = get_channel_layer()
        if layer is None:  # pragma: no cover - only when no layer is configured
            return
        async_to_sync(layer.group_send)(engagement_group(engagement_id), payload)
    except Exception:
        logger.warning("Failed to broadcast %s", payload.get("type"), exc_info=True)


def tunnel_updated(tunnel) -> None:
    from apps.api.serializers import TunnelSerializer

    _send(
        tunnel.engagement_id,
        {"type": "tunnel.updated", "tunnel": TunnelSerializer(tunnel).data},
    )


def tunnel_log(tunnel, log) -> None:
    _send(
        tunnel.engagement_id,
        {
            "type": "tunnel.log",
            "tunnel_id": tunnel.pk,
            "log": {
                "created_at": log.created_at.isoformat(),
                "level": log.level,
                "message": log.message,
                "source": log.source,
            },
        },
    )


def scan_updated(scan) -> None:
    from apps.api.serializers import ScanSerializer

    _send(scan.engagement_id, {"type": "scan.updated", "scan": ScanSerializer(scan).data})


def agent_updated(agent) -> None:
    from apps.api.serializers import AgentSerializer

    _send(agent.engagement_id, {"type": "agent.updated", "agent": AgentSerializer(agent).data})


def engine_status(engagement_id: int, *, attached: bool) -> None:
    _send(engagement_id, {"type": "engine.status", "attached": attached})
