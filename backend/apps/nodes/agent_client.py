"""
Synchronous RPC facade used by Celery task workers (and, sparingly, by
request-time code that needs a quick answer, e.g. console session setup)
to invoke a typed operation on a node's agent and wait for the result.

Celery workers are plain synchronous processes, so this does not use
asyncio: it publishes the command onto the agent's Channels group (which
the AgentConsumer -- running in the ASGI process -- relays out over the
live websocket) and then polls a short-lived Redis key that the consumer
writes the correlated response into.
"""
from __future__ import annotations

import json
import logging
import time

from asgiref.sync import async_to_sync
from django.conf import settings

from apps.common.exceptions import AgentOperationFailed, AgentUnavailable
from apps.common.redis_client import get_redis
from apps.nodes.consumers import connection_key, response_key
from apps.nodes.protocol import AgentRequest, AgentResponse, OperationType

logger = logging.getLogger("nodepilot.agent_client")


def is_agent_connected(node) -> bool:
    return get_redis().exists(connection_key(str(node.uuid))) == 1


def send_operation(
    node,
    operation: OperationType,
    resource_id: str,
    payload: dict | None = None,
    timeout: int | None = None,
) -> dict:
    """Sends a typed operation to `node`'s agent and blocks for the
    response. Raises AgentUnavailable if no agent is currently connected,
    or AgentOperationFailed if the agent reports an error."""
    agent = getattr(node, "agent", None)
    if agent is None or not agent.is_usable:
        raise AgentUnavailable(f"Node {node.name} has no active agent.")
    if not is_agent_connected(node):
        raise AgentUnavailable(f"Node {node.name}'s agent is not currently connected.")

    request = AgentRequest(operation=operation, resource_id=str(resource_id), payload=payload or {})
    timeout = timeout or settings.NODEPILOT["AGENT_RPC_TIMEOUT_SECONDS"]

    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    async_to_sync(layer.group_send)(
        f"agent.{node.uuid}",
        {"type": "agent.command", "message": request.to_wire()},
    )
    logger.info("Sent %s to node %s (request_id=%s)", operation, node.uuid, request.request_id)

    redis = get_redis()
    key = response_key(request.request_id)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = redis.get(key)
        if raw is not None:
            redis.delete(key)
            response = AgentResponse.from_wire(json.loads(raw))
            if not response.success:
                raise AgentOperationFailed(response.error or "The agent reported an unspecified error.", details=response.data)
            return response.data
        time.sleep(0.2)

    raise AgentUnavailable(f"Timed out waiting for node {node.name}'s agent to respond to {operation}.")
