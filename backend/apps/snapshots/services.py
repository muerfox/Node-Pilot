from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import InvalidStateTransition, ResourceLocked, StorageCapabilityUnsupported
from apps.jobs.models import JobType
from apps.jobs.services import create_job
from apps.organizations.services import check_and_reserve
from apps.snapshots.models import Snapshot, SnapshotStatus
from apps.storage.models import StorageCapability
from apps.virtual_machines.locks import storage_lock


def _assert_snapshot_capable(vm) -> None:
    unsupported = [d.storage.name for d in vm.disks.select_related("storage").all() if not d.storage.supports(StorageCapability.SNAPSHOT)]
    if unsupported:
        raise StorageCapabilityUnsupported(
            f"The following disks live on storage that does not support snapshots: {', '.join(unsupported)}",
            details={"disks": unsupported},
        )


@transaction.atomic
def create_snapshot(vm, *, name: str, description: str, requested_by) -> "Job":
    _assert_snapshot_capable(vm)
    check_and_reserve(vm.organization, vm.project, additional_snapshots=1)

    lock = storage_lock(vm)
    if not lock.acquire(blocking=False):
        raise ResourceLocked(f"VM {vm.name} has a storage operation in progress.")
    lock.release()

    snapshot = Snapshot.objects.create(vm=vm, name=name, description=description, status=SnapshotStatus.CREATING)
    job = create_job(type=JobType.SNAPSHOT_CREATE, resource_type="Snapshot", resource_id=str(snapshot.uuid), organization=vm.organization, node=vm.node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue(job.pk, snapshot.pk, "create"))
    return job


def delete_snapshot(snapshot: Snapshot, requested_by) -> "Job":
    # ERROR is included (unlike rollback, which needs a genuinely READY
    # snapshot) so a snapshot that failed mid-create -- or a delete/
    # rollback attempt that itself failed -- always has a way out rather
    # than becoming a permanently stuck, undeletable row. Mirrors
    # VMStatus's own delete-from-ERROR allowance (_ALLOWED_FROM[VM_DELETE]).
    if snapshot.status not in (SnapshotStatus.READY, SnapshotStatus.ERROR):
        raise InvalidStateTransition(f"Cannot delete a snapshot in status {snapshot.status}")
    job = create_job(type=JobType.SNAPSHOT_DELETE, resource_type="Snapshot", resource_id=str(snapshot.uuid), organization=snapshot.vm.organization, node=snapshot.vm.node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue(job.pk, snapshot.pk, "delete"))
    return job


def rollback_snapshot(snapshot: Snapshot, requested_by) -> "Job":
    if snapshot.status != SnapshotStatus.READY:
        raise InvalidStateTransition(f"Cannot roll back to a snapshot in status {snapshot.status}")
    job = create_job(type=JobType.SNAPSHOT_ROLLBACK, resource_type="Snapshot", resource_id=str(snapshot.uuid), organization=snapshot.vm.organization, node=snapshot.vm.node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue(job.pk, snapshot.pk, "rollback"))
    return job


def _enqueue(job_id: int, snapshot_id: int, op: str) -> None:
    from apps.snapshots.tasks import create_snapshot_task, delete_snapshot_task, rollback_snapshot_task

    {"create": create_snapshot_task, "delete": delete_snapshot_task, "rollback": rollback_snapshot_task}[op].delay(job_id, snapshot_id)
