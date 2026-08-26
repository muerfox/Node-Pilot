"""
Maps each typed OperationType (section 52) to its handler. This is the
complete, closed set of privileged actions the agent will ever perform on
behalf of the controller -- there is deliberately no fallback/default
case that could execute arbitrary payload content.
"""
from __future__ import annotations

import asyncio
import logging

from nodepilot_agent import console
from nodepilot_agent.config import AgentConfig
from nodepilot_agent.libvirt_client import LibvirtClient
from nodepilot_agent.operations import backup_ops, cloud_init_ops, disk_ops, network_ops, snapshot_ops, storage_ops, vm_ops
from nodepilot_agent.protocol import AgentRequest, AgentResponse, OperationType

logger = logging.getLogger("nodepilot_agent.dispatcher")


class Dispatcher:
    def __init__(self, config: AgentConfig, libvirt_client: LibvirtClient, send_console_data):
        self.config = config
        self.libvirt_client = libvirt_client
        self.send_console_data = send_console_data

    async def dispatch(self, request: AgentRequest) -> AgentResponse:
        try:
            data = await self._run(request)
            return AgentResponse.ok(request.request_id, data)
        except Exception as exc:  # noqa: BLE001 - every failure must produce a typed response, never crash the loop
            logger.exception("Operation %s failed", request.operation)
            return AgentResponse.fail(request.request_id, str(exc))

    async def _run(self, request: AgentRequest) -> dict:
        op = request.operation
        payload = request.payload
        resource_id = request.resource_id
        loop = asyncio.get_event_loop()
        lv = self.libvirt_client

        if op == OperationType.OPEN_CONSOLE:
            await console.open_session(payload["session_id"], resource_id, lv, self.send_console_data)
            return {}

        if op == OperationType.GET_HOST_INFO:
            return await loop.run_in_executor(None, lv.host_info)
        if op == OperationType.GET_DOMAIN_INFO:
            return await loop.run_in_executor(None, vm_ops.get_domain_info, resource_id, lv)

        if op == OperationType.CREATE_VM:
            return await loop.run_in_executor(None, vm_ops.create_vm, payload, lv)
        if op == OperationType.DELETE_VM:
            return await loop.run_in_executor(None, vm_ops.delete_vm, payload, resource_id, lv)
        if op == OperationType.START_VM:
            return await loop.run_in_executor(None, vm_ops.start_vm, resource_id, lv)
        if op == OperationType.SHUTDOWN_VM:
            return await loop.run_in_executor(None, vm_ops.shutdown_vm, resource_id, lv)
        if op == OperationType.STOP_VM:
            return await loop.run_in_executor(None, vm_ops.stop_vm, resource_id, lv)
        if op == OperationType.REBOOT_VM:
            return await loop.run_in_executor(None, vm_ops.reboot_vm, resource_id, lv)
        if op == OperationType.RESET_VM:
            return await loop.run_in_executor(None, vm_ops.reset_vm, resource_id, lv)
        if op == OperationType.PAUSE_VM:
            return await loop.run_in_executor(None, vm_ops.pause_vm, resource_id, lv)
        if op == OperationType.RESUME_VM:
            return await loop.run_in_executor(None, vm_ops.resume_vm, resource_id, lv)
        if op == OperationType.MIGRATE_VM:
            return await loop.run_in_executor(None, vm_ops.migrate_vm, payload, resource_id)

        if op == OperationType.CREATE_DISK:
            return await loop.run_in_executor(None, disk_ops.create_disk, payload)
        if op == OperationType.DELETE_DISK:
            return await loop.run_in_executor(None, disk_ops.delete_disk, payload)
        if op == OperationType.RESIZE_DISK:
            return await loop.run_in_executor(None, disk_ops.resize_disk, payload)
        if op == OperationType.CLONE_DISK:
            return await loop.run_in_executor(None, disk_ops.clone_disk, payload)
        if op == OperationType.ATTACH_DISK:
            return await loop.run_in_executor(None, disk_ops.attach_disk, payload, lv)
        if op == OperationType.DETACH_DISK:
            return await loop.run_in_executor(None, disk_ops.detach_disk, payload, lv)

        if op == OperationType.CREATE_NETWORK:
            return await loop.run_in_executor(None, network_ops.create_network, payload)
        if op == OperationType.DELETE_NETWORK:
            return await loop.run_in_executor(None, network_ops.delete_network, payload)
        if op == OperationType.ATTACH_NIC:
            return await loop.run_in_executor(None, network_ops.attach_nic, payload, lv)
        if op == OperationType.DETACH_NIC:
            return await loop.run_in_executor(None, network_ops.detach_nic, payload, lv)

        if op == OperationType.CREATE_SNAPSHOT:
            return await loop.run_in_executor(None, snapshot_ops.create_snapshot, payload, resource_id, lv)
        if op == OperationType.DELETE_SNAPSHOT:
            return await loop.run_in_executor(None, snapshot_ops.delete_snapshot, payload, resource_id, lv)
        if op == OperationType.ROLLBACK_SNAPSHOT:
            return await loop.run_in_executor(None, snapshot_ops.rollback_snapshot, payload, resource_id, lv)

        if op == OperationType.GET_STORAGE_POOL_INFO:
            return await loop.run_in_executor(None, storage_ops.get_storage_pool_info, payload)
        if op == OperationType.CREATE_STORAGE_POOL:
            return await loop.run_in_executor(None, storage_ops.create_storage_pool, payload)
        if op == OperationType.DELETE_STORAGE_POOL:
            return await loop.run_in_executor(None, storage_ops.delete_storage_pool, payload)

        if op == OperationType.GENERATE_CLOUD_INIT:
            return await loop.run_in_executor(None, cloud_init_ops.generate_cloud_init, payload, resource_id, self.config.cloud_init_workdir, lv)

        if op == OperationType.CREATE_BACKUP:
            return await loop.run_in_executor(None, backup_ops.create_backup, payload, resource_id)
        if op == OperationType.RESTORE_BACKUP:
            return await loop.run_in_executor(None, backup_ops.restore_backup, payload, resource_id)

        raise NotImplementedError(f"Unhandled operation: {op}")
