from __future__ import annotations

from nodepilot_agent.storage import get_backend


def create_disk(payload: dict) -> dict:
    backend = get_backend(payload["storage_type"], payload["storage_path"])
    # The disk_uuid (not the human-readable `name`) is used as the actual
    # volume identifier so two VMs both naming a disk "root" can never
    # collide on the same storage pool.
    volume_name = payload["disk_uuid"]
    info = backend.create_volume(volume_name, payload["size_bytes"], format=payload.get("format", "qcow2"))
    # `info.format` is what the backend actually produced -- LVM/LVM-thin/
    # ZFS always return "raw" regardless of what was requested (they're
    # block devices, not qcow2-capable files), so this is authoritative
    # and the controller must persist it, not the originally-requested
    # format, or the domain XML built later would declare the wrong
    # driver type for this disk.
    return {"volume_id": info.volume_id, "device": "", "size_bytes": info.size_bytes, "format": info.format}


def delete_disk(payload: dict) -> dict:
    backend = get_backend(payload["storage_type"], payload["storage_path"])
    backend.delete_volume(payload["volume_id"])
    return {}


def resize_disk(payload: dict) -> dict:
    backend = get_backend(payload["storage_type"], payload["storage_path"])
    backend.resize_volume(payload["volume_id"], payload["new_size_bytes"])
    return {}


def clone_disk(payload: dict) -> dict:
    backend = get_backend(payload["storage_type"], payload["storage_path"])
    info = backend.clone_volume(payload["source_volume_id"], payload["new_name"], linked=bool(payload.get("linked")))
    return {"volume_id": info.volume_id, "size_bytes": info.size_bytes}


def attach_disk(payload: dict, libvirt_client) -> dict:
    from nodepilot_agent.domain_xml import build_disk_xml

    xml = build_disk_xml(
        volume_path=payload["volume_id"], device=payload["device"], bus=payload.get("bus", "VIRTIO"),
        storage_type=payload.get("storage_type"), format=payload.get("format"),
    )
    libvirt_client.attach_device(payload["domain_uuid"], xml)
    return {}


def detach_disk(payload: dict, libvirt_client) -> dict:
    from nodepilot_agent.domain_xml import build_disk_xml

    xml = build_disk_xml(
        volume_path=payload["volume_id"], device=payload["device"], bus=payload.get("bus", "VIRTIO"),
        storage_type=payload.get("storage_type"), format=payload.get("format"),
    )
    libvirt_client.detach_device(payload["domain_uuid"], xml)
    return {}
