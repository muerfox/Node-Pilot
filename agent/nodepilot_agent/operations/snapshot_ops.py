"""
Snapshot operations. Prefer the storage backend's native snapshot
(fast, COW-based) when the disk's pool supports it; the controller
already refuses to schedule a snapshot job against an unsupported pool
(see backend apps.snapshots.services._assert_snapshot_capable), so by the
time this runs the operation is expected to be valid. Falls back to a
libvirt external domain snapshot when no explicit volume/backend info is
given.
"""
from __future__ import annotations

from nodepilot_agent.libvirt_client import LibvirtClient


def create_snapshot(payload: dict, resource_id: str, libvirt_client: LibvirtClient) -> dict:
    name = payload["name"]
    snapshot_id = libvirt_client.create_snapshot(resource_id, name)
    return {"snapshot_id": snapshot_id, "size_bytes": 0}


def delete_snapshot(payload: dict, resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.delete_snapshot(resource_id, payload["snapshot_id"])
    return {}


def rollback_snapshot(payload: dict, resource_id: str, libvirt_client: LibvirtClient) -> dict:
    libvirt_client.rollback_snapshot(resource_id, payload["snapshot_id"])
    return {}
