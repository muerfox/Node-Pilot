from __future__ import annotations

import base64
import logging
import uuid

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer, AsyncWebsocketConsumer

logger = logging.getLogger("nodepilot.vm_transport")


class VMConsumer(AsyncJsonWebsocketConsumer):
    """/ws/vms/{vm_uuid} -- status/metrics updates for a single VM."""

    async def connect(self):
        self.vm_uuid = self.scope["url_route"]["kwargs"]["vm_uuid"]
        vm = await self._get_vm()
        if vm is None or not await self._can_view(vm):
            await self.close(code=4403)
            return
        self.group_name = f"vm.{self.vm_uuid}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def vm_status(self, event):
        await self.send_json(event["data"])

    @database_sync_to_async
    def _get_vm(self):
        from apps.virtual_machines.models import VirtualMachine

        return VirtualMachine.objects.select_related("organization").filter(uuid=self.vm_uuid).first()

    @database_sync_to_async
    def _can_view(self, vm) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        from apps.permissions.policies import has_permission

        return has_permission(user, vm.organization, "vm.view")


class ConsoleConsumer(AsyncWebsocketConsumer):
    """
    /ws/console/{vm_uuid} -- interactive graphical (noVNC-compatible) or
    serial console (section 21). Never exposes the QEMU console directly:
    the browser talks only to this authenticated relay, which forwards
    base64-framed console bytes to/from the agent over the existing
    agent command connection, correlated by a short-lived session id.
    """

    async def connect(self):
        self.vm_uuid = self.scope["url_route"]["kwargs"]["vm_uuid"]
        vm = await self._get_vm()
        if vm is None or not await self._can_console(vm):
            await self.close(code=4403)
            return
        if vm.status != "RUNNING":
            await self.close(code=4409)
            return

        self.vm = vm
        self.session_id = uuid.uuid4().hex
        self.group_name = f"console.{self.session_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        opened = await self._open_console()
        if not opened:
            await self.close(code=4502)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        if hasattr(self, "vm"):
            await self._send_to_agent({"type": "console_close", "session_id": self.session_id})

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data is not None:
            payload = base64.b64encode(bytes_data).decode()
        elif text_data is not None:
            payload = text_data
        else:
            return
        await self._send_to_agent({"type": "console_input", "session_id": self.session_id, "data": payload})

    async def console_data(self, event):
        await self.send(bytes_data=base64.b64decode(event["data"]))

    async def _send_to_agent(self, message: dict) -> None:
        await self.channel_layer.group_send(f"agent.{self.vm.node.uuid}", {"type": "agent.command", "message": message})

    async def _open_console(self) -> bool:
        from apps.nodes import agent_client
        from apps.nodes.protocol import OperationType

        try:
            await database_sync_to_async(agent_client.send_operation)(
                self.vm.node, OperationType.OPEN_CONSOLE, resource_id=str(self.vm.uuid), payload={"session_id": self.session_id}
            )
            return True
        except Exception:
            logger.exception("Failed to open console for VM %s", self.vm_uuid)
            return False

    @database_sync_to_async
    def _get_vm(self):
        from apps.virtual_machines.models import VirtualMachine

        return VirtualMachine.objects.select_related("organization", "node").filter(uuid=self.vm_uuid).first()

    @database_sync_to_async
    def _can_console(self, vm) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        from apps.permissions.policies import has_permission

        return has_permission(user, vm.organization, "vm.console")


def broadcast_vm_status(vm) -> None:
    try:
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"vm.{vm.uuid}",
            {"type": "vm.status", "data": {"uuid": str(vm.uuid), "status": vm.status, "provisioning_state": vm.provisioning_state}},
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to broadcast VM status for %s", vm.uuid)
