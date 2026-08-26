from __future__ import annotations

import os

from nodepilot_agent.storage import get_backend


def get_storage_pool_info(payload: dict) -> dict:
    backend = get_backend(payload["storage_type"], payload["storage_path"])
    info = backend.pool_info()
    return {"capacity_bytes": info.capacity_bytes, "used_bytes": info.used_bytes, "available_bytes": info.available_bytes}


def create_storage_pool(payload: dict) -> dict:
    storage_type = payload["storage_type"]
    if storage_type == "DIRECTORY":
        os.makedirs(payload["storage_path"], exist_ok=True)
        return {}
    # LVM/LVM-thin/ZFS/NFS pools are provisioned out-of-band (they require
    # host-specific decisions -- disk selection, RAID/mirroring, NFS
    # mount options -- that don't belong in an automated agent action);
    # NodePilot registers the already-existing pool instead.
    raise NotImplementedError(f"Creating a {storage_type} pool must be done on the host; register the existing pool instead.")


def delete_storage_pool(payload: dict) -> dict:
    raise NotImplementedError("Deleting a storage pool is an intentionally manual, host-level operation.")
