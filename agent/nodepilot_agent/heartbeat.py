"""
Periodic heartbeat (section 53). Runs as its own asyncio task, independent
of the command websocket -- a heartbeat gap is what the controller uses to
flip a node OFFLINE, so it must keep going even if the command channel is
mid-reconnect.
"""
from __future__ import annotations

import asyncio
import logging
import platform

import httpx

from nodepilot_agent.config import AgentConfig
from nodepilot_agent.libvirt_client import LIBVIRT_AVAILABLE, LibvirtClient
from nodepilot_agent.metrics import collect_host_metrics

logger = logging.getLogger("nodepilot_agent.heartbeat")


def _running_vm_count(libvirt_client: LibvirtClient) -> int:
    if not LIBVIRT_AVAILABLE:
        return 0
    try:
        conn = libvirt_client.connect()
        return len(conn.listAllDomains())
    except Exception:  # pragma: no cover - best-effort; never blocks the heartbeat
        logger.exception("Failed to count domains for heartbeat")
        return 0


async def heartbeat_loop(config: AgentConfig, libvirt_client: LibvirtClient, stop_event: asyncio.Event) -> None:
    headers = {"Authorization": f"Agent {config.agent_token}"}
    async with httpx.AsyncClient(verify=config.tls_verify, timeout=10.0) as client:
        while not stop_event.is_set():
            try:
                host = await asyncio.get_event_loop().run_in_executor(None, collect_host_metrics)
                payload = {
                    "agent_version": config.agent_version,
                    "protocol_version": config.protocol_version,
                    "kernel": platform.release(),
                    "architecture": platform.machine(),
                    "cpu": {**host["cpu"], "model": platform.processor() or "unknown", "cores": host["cpu"]["count"], "sockets": 1, "threads": 1},
                    "memory": host["memory"],
                    "storage": host["storage"],
                    "vms": await asyncio.get_event_loop().run_in_executor(None, _running_vm_count, libvirt_client),
                }
                response = await client.post(config.controller_heartbeat_url, json=payload, headers=headers)
                if response.status_code >= 400:
                    logger.warning("Heartbeat rejected (%s): %s", response.status_code, response.text[:500])
            except Exception:
                logger.exception("Heartbeat failed")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=config.heartbeat_interval_seconds)
            except asyncio.TimeoutError:
                pass
