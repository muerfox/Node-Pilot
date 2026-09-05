from __future__ import annotations

from celery import shared_task

from apps.jobs.models import Job, JobStatus
from apps.jobs.services import job_run, transition
from apps.jobs.tasks import JobBoundTask
from apps.storage.models import StoragePool, StoragePoolStatus, StorageType
from apps.storage.services import refresh_storage_pool_info


@shared_task(bind=True, base=JobBoundTask)
def create_storage_pool_task(self, job_id: int, pool_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    pool = StoragePool.objects.select_related("node", "node__organization").get(pk=pool_id)
    try:
        with job_run(job, f"Registering storage pool {pool.name}"):
            if pool.type == StorageType.DIRECTORY:
                from apps.nodes import agent_client
                from apps.nodes.protocol import OperationType

                agent_client.send_operation(
                    pool.node, OperationType.CREATE_STORAGE_POOL, resource_id=str(pool.uuid),
                    payload={"storage_type": pool.type, "storage_path": pool.path},
                )
            # LVM/LVM-thin/ZFS/NFS/Ceph-RBD pools are provisioned
            # out-of-band on the host (see agent storage_ops.create_storage_pool);
            # NodePilot only registers the already-existing pool, so there's
            # nothing to create for those types -- go straight to fetching
            # real capacity/usage below.
            refresh_storage_pool_info(pool)
        transition(job, JobStatus.SUCCESS, message="Storage pool registered")
        _emit(pool, "STORAGE_POOL_CREATED")
    except Exception as exc:
        pool.status = StoragePoolStatus.ERROR
        pool.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        _emit(pool, "STORAGE_POOL_ERROR", error=str(exc))
        raise


@shared_task(name="storage.refresh_storage_pools")
def refresh_storage_pools_task() -> int:
    """Runs on a Celery Beat interval so a pool's reported capacity/usage
    doesn't sit frozen at whatever it was when last touched -- and so a
    pool that goes unreachable (node offline, path removed, unsupported
    backend) is reflected as ERROR rather than silently stale ONLINE."""
    from apps.nodes.models import NodeStatus

    refreshed = 0
    for pool in StoragePool.objects.filter(enabled=True).select_related("node"):
        if pool.node.effective_status() != NodeStatus.ONLINE:
            continue
        try:
            refresh_storage_pool_info(pool)
            refreshed += 1
        except Exception:  # noqa: BLE001 - one bad pool must never stop the sweep
            StoragePool.objects.filter(pk=pool.pk).update(status=StoragePoolStatus.ERROR)
    return refreshed


def _emit(pool: StoragePool, event_type: str, **metadata) -> None:
    from apps.events.services import emit_event

    try:
        emit_event(
            type=event_type, severity="INFO" if event_type != "STORAGE_POOL_ERROR" else "CRITICAL", resource_type="StoragePool",
            resource_id=str(pool.uuid), organization=pool.node.organization, metadata={"name": pool.name, **metadata},
        )
    except Exception:  # pragma: no cover
        pass
