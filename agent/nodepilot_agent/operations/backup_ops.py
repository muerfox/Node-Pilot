"""
Backup/restore. LOCAL and NFS targets are implemented directly (a target
path the agent can write files to); S3/MinIO/Ceph targets require an
object-storage client this MVP agent does not ship, so they raise a clear
NotImplementedError rather than silently no-op'ing or faking success
(rule: never claim an operation succeeded that didn't happen).
"""
from __future__ import annotations

import hashlib
import os

from nodepilot_agent.storage.base import StorageOperationError, run

_FILE_BASED_TARGETS = {"LOCAL", "NFS"}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(payload: dict, resource_id: str) -> dict:
    target_type = payload["target_type"]
    if target_type not in _FILE_BASED_TARGETS:
        raise NotImplementedError(f"Backup target type {target_type!r} is not supported by this agent version.")

    target_dir = payload["target"]["path"]
    os.makedirs(target_dir, exist_ok=True)

    volume_id = payload.get("volume_id")
    if not volume_id:
        raise StorageOperationError("create_backup requires the VM's primary disk volume_id in the payload.")

    dest = os.path.join(target_dir, f"{payload['backup_uuid']}.qcow2")
    run(["qemu-img", "convert", "-O", "qcow2", volume_id, dest])
    checksum = _sha256_file(dest)
    size_bytes = os.path.getsize(dest)
    return {"backup_ref": dest, "size_bytes": size_bytes, "checksum": checksum}


def restore_backup(payload: dict, resource_id: str) -> dict:
    target_type = payload["target_type"]
    if target_type not in _FILE_BASED_TARGETS:
        raise NotImplementedError(f"Backup target type {target_type!r} is not supported by this agent version.")

    backup_ref = payload["backup_ref"]
    destination_volume = payload.get("volume_id") or payload.get("destination_volume_id")
    if not destination_volume:
        raise StorageOperationError("restore_backup requires the destination volume_id in the payload.")

    if not os.path.exists(backup_ref):
        raise StorageOperationError(f"Backup artifact not found: {backup_ref}")
    run(["qemu-img", "convert", "-O", "qcow2", backup_ref, destination_volume])
    return {}
