"""
StoragePool creation/refresh (section 14). Registering a pool through the
API used to do nothing but insert a database row: capacity_bytes,
used_bytes, available_bytes and status are all read-only fields implying
they're system-reported, and the agent already has a fully working
GET_STORAGE_POOL_INFO operation to report them (plus CREATE_STORAGE_POOL,
which for a DIRECTORY pool actually creates the directory) -- but nothing
ever called either one, so every pool sat at capacity_bytes=0 forever and
a DIRECTORY pool's path was never actually created on the host.
"""
from __future__ import annotations

from django.db import transaction

from apps.jobs.models import JobType
from apps.jobs.services import create_job
from apps.storage.models import StoragePool, StoragePoolStatus


def create_storage_pool(
    *, node, name: str, type: str, path: str, shared: bool, enabled: bool,
    capabilities: list[str] | None, requested_by,
) -> tuple[StoragePool, "Job"]:
    """Creates the StoragePool row (status OFFLINE until the agent confirms
    it) and dispatches provisioning/info-fetch. The HTTP handler never
    blocks on the actual node round-trip."""
    pool = StoragePool.objects.create(
        node=node, name=name, type=type, path=path, shared=shared, enabled=enabled,
        capabilities=capabilities or [], status=StoragePoolStatus.OFFLINE,
    )
    job = create_job(type=JobType.STORAGE_POOL_CREATE, resource_type="StoragePool", resource_id=str(pool.uuid), organization=node.organization, node=node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue_create(job.pk, pool.pk))
    return pool, job


def refresh_storage_pool_info(pool: StoragePool) -> StoragePool:
    """Fetches live capacity/usage from the node's agent via
    GET_STORAGE_POOL_INFO and updates the pool row. Raises whatever
    agent_client.send_operation raises (AgentUnavailable,
    AgentOperationFailed) on failure -- callers are responsible for
    deciding what that means for `status`."""
    from apps.nodes import agent_client
    from apps.nodes.protocol import OperationType

    info = agent_client.send_operation(
        pool.node, OperationType.GET_STORAGE_POOL_INFO, resource_id=str(pool.uuid),
        payload={"storage_type": pool.type, "storage_path": pool.path},
    )
    pool.capacity_bytes = info["capacity_bytes"]
    pool.used_bytes = info["used_bytes"]
    pool.available_bytes = info["available_bytes"]
    pool.status = StoragePoolStatus.ONLINE
    pool.save(update_fields=["capacity_bytes", "used_bytes", "available_bytes", "status", "updated_at"])
    return pool


def _enqueue_create(job_id: int, pool_id: int) -> None:
    from apps.storage.tasks import create_storage_pool_task

    create_storage_pool_task.delay(job_id, pool_id)
