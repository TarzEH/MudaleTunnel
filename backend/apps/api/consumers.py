"""WebSocket consumer for live engagement state.

This is what makes the CLI and the dashboard feel like one tool: a tunnel
started from the terminal appears in the browser immediately, because both
write to the database and the engine broadcasts the resulting state here.

Authorisation is checked on connect *and* is per-engagement — a socket is only
accepted for an engagement the authenticated user is a member of. v2 accepted
every handshake unconditionally, so any page a browser visited could open a
socket and read live tunnel state.
"""

from __future__ import annotations

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)

# Close codes (4000+ is the application-defined range).
CLOSE_UNAUTHENTICATED = 4001
CLOSE_FORBIDDEN = 4003
CLOSE_NOT_FOUND = 4004


def engagement_group(engagement_id: int | str) -> str:
    return f"engagement.{engagement_id}"


class EngagementConsumer(AsyncJsonWebsocketConsumer):
    """Streams tunnel, scan, agent and engine events for one engagement."""

    async def connect(self) -> None:
        self.engagement_id = self.scope["url_route"]["kwargs"]["engagement_id"]
        user = self.scope.get("user")

        if user is None or not user.is_authenticated:
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        if not await self._may_view(user, self.engagement_id):
            # Same code whether the engagement is missing or simply not theirs,
            # so a socket cannot be used to enumerate engagement ids.
            await self.close(code=CLOSE_FORBIDDEN)
            return

        self.group_name = engagement_group(self.engagement_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send_json({"type": "connected", "engagement": int(self.engagement_id)})

    async def disconnect(self, code) -> None:
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def receive_json(self, content, **kwargs) -> None:
        """The client is a listener; the only accepted message is a keepalive.

        Anything else is ignored rather than acted on — this socket must never
        become a second, unaudited command channel.
        """
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    # ── Group message handlers ──────────────────────────────────────────
    #
    # Named to match the "type" used by the broadcast helpers below; channels
    # dispatches on that name with dots replaced by underscores.

    async def tunnel_updated(self, event) -> None:
        await self.send_json({"type": "tunnel.updated", "tunnel": event["tunnel"]})

    async def tunnel_log(self, event) -> None:
        await self.send_json(
            {"type": "tunnel.log", "tunnel_id": event["tunnel_id"], "log": event["log"]}
        )

    async def scan_updated(self, event) -> None:
        await self.send_json({"type": "scan.updated", "scan": event["scan"]})

    async def agent_updated(self, event) -> None:
        await self.send_json({"type": "agent.updated", "agent": event["agent"]})

    async def engine_status(self, event) -> None:
        await self.send_json({"type": "engine.status", "attached": event["attached"]})

    # ── Helpers ─────────────────────────────────────────────────────────

    @database_sync_to_async
    def _may_view(self, user, engagement_id) -> bool:
        from apps.engagements.models import Engagement

        try:
            engagement_pk = int(engagement_id)
        except (TypeError, ValueError):
            return False
        return Engagement.objects.visible_to(user).filter(pk=engagement_pk).exists()
