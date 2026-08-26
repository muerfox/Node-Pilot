from __future__ import annotations

from nodepilot_agent.domain_xml import build_domain_xml
from nodepilot_agent.libvirt_client import LibvirtClient


def create_vm(payload: dict, libvirt_client: LibvirtClient) -> dict:
    xml = build_domain_xml(payload)
    domain_uuid = libvirt_client.define_domain(xml)
    return {"domain_uuid": domain_uuid}


def delete_vm(payload: dict, resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.undefine_domain(resource_id, remove_storage=bool(payload.get("delete_disks")))
    return {}


def start_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.start_domain(resource_id)
    return {}


def shutdown_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.graceful_shutdown(resource_id)
    return {}


def stop_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.force_stop(resource_id)
    return {}


def reboot_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.reboot(resource_id)
    return {}


def reset_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.reset(resource_id)
    return {}


def pause_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.suspend(resource_id)
    return {}


def resume_vm(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.resume(resource_id)
    return {}


def get_domain_info(resource_id: str, libvirt_client: LibvirtClient) -> dict:
    return libvirt_client.domain_info(resource_id)


def migrate_vm(payload: dict, resource_id: str) -> dict:
    # The controller does not send this yet (see backend
    # apps.virtual_machines.services.migrate_vm) -- live migration is a
    # Phase 9 feature. Kept here so the operation is at least a defined,
    # explicit no-op rather than an unrecognized message if it ever is.
    raise NotImplementedError("Live migration is not implemented in this agent version.")
