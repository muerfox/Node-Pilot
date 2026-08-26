"""
Entrypoint for the `nodepilot-agent` process. Runs two concurrent
asyncio tasks for the lifetime of the process:

  * the heartbeat loop (HTTP POST every heartbeat_interval_seconds)
  * the command transport (persistent websocket, auto-reconnecting)

Both share one LibvirtClient. A SIGTERM/SIGINT triggers a clean shutdown
of both loops -- this is what systemd sends on `systemctl stop`.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from nodepilot_agent.config import load_config
from nodepilot_agent.heartbeat import heartbeat_loop
from nodepilot_agent.libvirt_client import LibvirtClient
from nodepilot_agent.logging_utils import configure_logging
from nodepilot_agent.transport import run_transport

logger = logging.getLogger("nodepilot_agent.main")


async def _main(config_path: str | None) -> None:
    config = load_config(config_path)
    configure_logging(config.log_level)
    logger.info("Starting NodePilot Agent %s for node %s", config.agent_version, config.node_id)

    libvirt_client = LibvirtClient()
    stop_event = asyncio.Event()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # pragma: no cover - Windows dev environments
            pass

    await asyncio.gather(
        heartbeat_loop(config, libvirt_client, stop_event),
        run_transport(config, libvirt_client, stop_event),
    )

    libvirt_client.close()
    logger.info("NodePilot Agent stopped")


def run() -> None:
    parser = argparse.ArgumentParser(prog="nodepilot-agent")
    parser.add_argument("--config", help="Path to agent.yaml (default: /etc/nodepilot/agent.yaml)")
    args = parser.parse_args()
    asyncio.run(_main(args.config))


if __name__ == "__main__":
    run()
