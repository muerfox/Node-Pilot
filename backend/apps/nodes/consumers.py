from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.common.redis_client import get_redis

logger = logging.getLogger("nodepilot.agent_transport")

CONN_KEY_PREFIX = "nodepilot:agent:conn:"
RESPONSE_KEY_PREFIX = "nodepilot:agent:response:"


def connection_key(node_uuid: str) -> str:
    return f"{CONN_KEY_PREFIX}{node_uuid}"


def response_key(request_id: str) -> str:
    return f"{RESPONSE_KEY_PREFIX}{request_id}"


class AgentConsumer(AsyncWebsocketConsumer):
    """
    /ws/agent/{node_uuid}/?token=<agent-token>

    The persistent, agent-initiated connection NodePilot uses to push
    typed commands (section 52) to a hypervisor and receive responses.
    The controller never opens an inbound connection to the agent -- this
    keeps the hypervisor reachable through NAT/firewalls with no inbound
    port required, and means the controller never needs SSH access.
    """

    async def connect(self):
        self.node_uuid = self.scope["url_route"]["kwargs"]["node_uuid"]
        query = parse_qs(self.scope.get("query_string", b"").decode())
        raw_token = (query.get("token") or [None])[0]

        agent = await self._authenticate(self.node_uuid, raw_token)
        if agent is None:
            await self.close(code=4401)
            return

        self.agent_id = agent.pk
        self.group_name = f"agent.{self.node_uuid}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        get_redis().set(connection_key(self.node_uuid), "1", ex=120)
        logger.info("Agent connected for node %s", self.node_uuid)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            get_redis().delete(connection_key(self.node_uuid))
            logger.info("Agent disconnected for node %s (code=%s)", self.node_uuid, code)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            message = json.loads(text_data)
        except ValueError:
            logger.warning("Malformed message from agent %s", self.node_uuid)
            return

        # Keep the connection-alive TTL fresh on any traffic.
        get_redis().expire(connection_key(self.node_uuid), 120)

        msg_type = message.get("type", "response")
        if msg_type == "console_data":
            await self._relay_console_data(message)
            return

        request_id = message.get("request_id")
        if not request_id:
            logger.warning("Agent %s sent a message with no request_id", self.node_uuid)
            return
        get_redis().set(response_key(request_id), json.dumps(message), ex=60)

    async def agent_command(self, event):
        """Relays a command from the controller (sent via channel_layer
        group_send in apps.nodes.agent_client) out over the actual
        websocket to the connected agent process."""
        await self.send(text_data=json.dumps(event["message"]))

    async def _relay_console_data(self, message):
        session_id = message.get("session_id")
        if not session_id:
            return
        await self.channel_layer.group_send(
            f"console.{session_id}",
            {"type": "console.data", "data": message.get("data", "")},
        )

    @database_sync_to_async
    def _authenticate(self, node_uuid: str, raw_token: str | None):
        if not raw_token:
            return None
        from apps.nodes.models import Agent, AgentStatus

        token_hash = Agent.hash_token(raw_token)
        agent = Agent.objects.select_related("node").filter(token_hash=token_hash, status=AgentStatus.ACTIVE).first()
        if agent is None or str(agent.node.uuid) != node_uuid:
            return None
        return agent


class NodeStatusConsumer(AsyncWebsocketConsumer):
    """/ws/nodes/{node_uuid} -- UI-facing feed of node status/metrics
    changes. Distinct from AgentConsumer, which is the agent's own
    outbound control connection."""

    async def connect(self):
        self.node_uuid = self.scope["url_route"]["kwargs"]["node_uuid"]
        node = await self._get_node()
        if node is None or not await self._user_can_view(node):
            await self.close(code=4403)
            return
        self.group_name = f"node_status.{self.node_uuid}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def node_status(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    @database_sync_to_async
    def _get_node(self):
        from apps.nodes.models import Node

        return Node.objects.select_related("organization").filter(uuid=self.node_uuid).first()

    @database_sync_to_async
    def _user_can_view(self, node) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        from apps.permissions.policies import has_permission

        return has_permission(user, node.organization, "node.view")


def broadcast_node_status(node) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"node_status.{node.uuid}",
            {
                "type": "node.status",
                "data": {
                    "uuid": str(node.uuid),
                    "status": node.effective_status(),
                    "memory_available_mb": node.memory_available_mb,
                    "storage_available_gb": node.storage_available_gb,
                    "reported_vm_count": node.reported_vm_count,
                },
            },
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to broadcast node status for %s", node.uuid)
