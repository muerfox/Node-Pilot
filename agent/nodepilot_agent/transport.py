"""
Persistent, agent-initiated websocket connection to the controller
(section 52/21). The agent always dials out -- the controller never opens
an inbound connection to the hypervisor, so no inbound port needs to be
exposed and the agent works fine behind NAT/firewalls.

Reconnects with exponential backoff on any disconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging

import websockets

from nodepilot_agent import console
from nodepilot_agent.config import AgentConfig
from nodepilot_agent.libvirt_client import LibvirtClient
from nodepilot_agent.operations.dispatcher import Dispatcher
from nodepilot_agent.protocol import AgentRequest

logger = logging.getLogger("nodepilot_agent.transport")


async def run_transport(config: AgentConfig, libvirt_client: LibvirtClient, stop_event: asyncio.Event) -> None:
    backoff = config.reconnect_backoff_seconds

    while not stop_event.is_set():
        try:
            async with websockets.connect(config.controller_ws_url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("Connected to controller command channel")
                backoff = config.reconnect_backoff_seconds  # reset after a successful connection

                async def send_console_data(session_id: str, data_b64: str) -> None:
                    await ws.send(json.dumps({"type": "console_data", "session_id": session_id, "data": data_b64}))

                dispatcher = Dispatcher(config, libvirt_client, send_console_data)
                await _receive_loop(ws, dispatcher, stop_event)

        except (websockets.ConnectionClosed, OSError) as exc:
            logger.warning("Command channel disconnected (%s); reconnecting in %.1fs", exc, backoff)
        except Exception:
            logger.exception("Unexpected transport error; reconnecting in %.1fs", backoff)

        if stop_event.is_set():
            break
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, config.reconnect_backoff_max_seconds)


async def _receive_loop(ws, dispatcher: Dispatcher, stop_event: asyncio.Event) -> None:
    async for raw_message in ws:
        if stop_event.is_set():
            return
        try:
            message = json.loads(raw_message)
        except ValueError:
            logger.warning("Received malformed message from controller")
            continue

        msg_type = message.get("type", "request")
        if msg_type == "console_input":
            await console.feed_input(message["session_id"], message["data"])
            continue
        if msg_type == "console_close":
            await console.close_session(message["session_id"])
            continue

        try:
            request = AgentRequest.from_wire(message)
        except (KeyError, ValueError) as exc:
            logger.warning("Rejecting malformed operation request: %s", exc)
            continue

        # Fire-and-forget: operations run concurrently so a slow one (e.g.
        # a multi-GB disk clone) never blocks heartbeats or other commands.
        asyncio.ensure_future(_handle(ws, dispatcher, request))


async def _handle(ws, dispatcher: Dispatcher, request: AgentRequest) -> None:
    response = await dispatcher.dispatch(request)
    try:
        await ws.send(json.dumps(response.to_wire()))
    except websockets.ConnectionClosed:
        logger.warning("Could not send response for %s: connection closed", request.request_id)
