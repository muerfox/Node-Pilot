from __future__ import annotations

import os
import shutil

from nodepilot_agent.storage import get_backend
from nodepilot_agent.storage.base import StorageOperationError, run


def create_disk(payload: dict, config=None) -> dict:
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
    if payload.get("image_uuid"):
        # Deploying from a Template (section 16): seed the blank volume
        # just created with the template's base image instead of leaving
        # it empty.
        if config is None:
            raise StorageOperationError("Cannot seed a disk from an image: no agent config (controller URL/token) available.")
        _seed_from_image(
            volume_id=info.volume_id, target_format=info.format, image_uuid=payload["image_uuid"],
            image_format=payload.get("image_format", ""), expected_sha256=payload.get("image_sha256", ""), config=config,
        )
    return {"volume_id": info.volume_id, "device": "", "size_bytes": info.size_bytes, "format": info.format}


def _seed_from_image(*, volume_id: str, target_format: str, image_uuid: str, image_format: str, expected_sha256: str, config) -> None:
    from nodepilot_agent.image_fetch import download_image

    downloaded_path = download_image(config, image_uuid, expected_sha256)
    try:
        # -n: write into the volume create_volume already made above
        # (sized to what was actually requested) instead of letting
        # qemu-img create/resize a target of its own to match the source
        # image's size -- the requested disk can legitimately be larger
        # than the base image (the guest just sees extra free space).
        args = ["qemu-img", "convert", "-n"]
        if image_format:
            args += ["-f", image_format]
        args += ["-O", target_format, downloaded_path, volume_id]
        run(args, timeout=3600)
    finally:
        shutil.rmtree(os.path.dirname(downloaded_path), ignore_errors=True)


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
