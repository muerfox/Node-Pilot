"""
Interactive console relay (section 21). The browser never talks to QEMU
directly: NodePilot's ConsoleConsumer (controller) opens a session here,
and this module pumps bytes between the domain's local VNC socket
(127.0.0.1-only, per the `listen="127.0.0.1"` in domain_xml.build_domain_xml)
and the persistent agent<->controller websocket, base64-framed and tagged
with a session id so multiple consoles can share one connection.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re

from nodepilot_agent.libvirt_client import LibvirtClient, LibvirtOperationError

logger = logging.getLogger("nodepilot_agent.console")

_VNC_PORT_RE = re.compile(r'<graphics[^>]*type=["\']vnc["\'][^>]*port=["\'](\d+)["\']')


class ConsoleSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.inbound: asyncio.Queue[bytes] = asyncio.Queue()
        self.task: asyncio.Task | None = None
        self.closed = asyncio.Event()


_sessions: dict[str, ConsoleSession] = {}


def _vnc_port(libvirt_client: LibvirtClient, domain_uuid: str) -> int:
    with libvirt_client.domain(domain_uuid) as dom:
        xml = dom.XMLDesc(0)
    match = _VNC_PORT_RE.search(xml)
    if not match or match.group(1) == "-1":
        raise LibvirtOperationError("Domain has no active VNC port (is it running?).")
    return int(match.group(1))


async def open_session(session_id: str, domain_uuid: str, libvirt_client: LibvirtClient, send_console_data) -> None:
    if session_id in _sessions:
        return
    session = ConsoleSession(session_id)
    _sessions[session_id] = session
    session.task = asyncio.ensure_future(_run_session(session, domain_uuid, libvirt_client, send_console_data))


async def feed_input(session_id: str, data_b64: str) -> None:
    session = _sessions.get(session_id)
    if session is not None:
        await session.inbound.put(base64.b64decode(data_b64))


async def close_session(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session is not None:
        session.closed.set()
        if session.task:
            session.task.cancel()


async def _run_session(session: ConsoleSession, domain_uuid: str, libvirt_client: LibvirtClient, send_console_data) -> None:
    try:
        port = await asyncio.get_event_loop().run_in_executor(None, _vnc_port, libvirt_client, domain_uuid)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except Exception:
        logger.exception("Failed to open console session %s", session.session_id)
        _sessions.pop(session.session_id, None)
        return

    async def pump_outbound():
        try:
            while not session.closed.is_set():
                chunk = await reader.read(65536)
                if not chunk:
                    break
                await send_console_data(session.session_id, base64.b64encode(chunk).decode())
        except (asyncio.CancelledError, ConnectionResetError):
            pass

    async def pump_inbound():
        try:
            while not session.closed.is_set():
                chunk = await session.inbound.get()
                writer.write(chunk)
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            pass

    try:
        await asyncio.gather(pump_outbound(), pump_inbound())
    finally:
        writer.close()
        _sessions.pop(session.session_id, None)
