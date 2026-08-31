from __future__ import annotations

from celery import shared_task

from apps.jobs.models import Job, JobStatus
from apps.jobs.services import job_run, transition
from apps.jobs.tasks import JobBoundTask
from apps.nodes import agent_client
from apps.nodes.protocol import OperationType
from apps.snapshots.models import Snapshot, SnapshotStatus
from apps.virtual_machines.locks import lifecycle_lock, storage_lock


@shared_task(bind=True, base=JobBoundTask)
def create_snapshot_task(self, job_id: int, snapshot_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    snapshot = Snapshot.objects.select_related("vm", "vm__node").get(pk=snapshot_id)
    vm = snapshot.vm
    try:
        with storage_lock(vm):
            with job_run(job, f"Creating snapshot {snapshot.name}"):
                data = agent_client.send_operation(
                    vm.node, OperationType.CREATE_SNAPSHOT, resource_id=str(vm.uuid),
                    payload={"snapshot_uuid": str(snapshot.uuid), "name": snapshot.name},
                )
                snapshot.agent_snapshot_id = data.get("snapshot_id", "")
                snapshot.size_bytes = data.get("size_bytes", 0)
                snapshot.status = SnapshotStatus.READY
                snapshot.save(update_fields=["agent_snapshot_id", "size_bytes", "status"])
        transition(job, JobStatus.SUCCESS, message="Snapshot created")
        _emit(vm, "VM_SNAPSHOT_CREATED", snapshot_name=snapshot.name)
    except Exception as exc:
        snapshot.status = SnapshotStatus.ERROR
        snapshot.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def delete_snapshot_task(self, job_id: int, snapshot_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    snapshot = Snapshot.objects.select_related("vm", "vm__node").get(pk=snapshot_id)
    vm = snapshot.vm
    status_before_attempt = snapshot.status
    try:
        with storage_lock(vm):
            with job_run(job, f"Deleting snapshot {snapshot.name}"):
                snapshot.status = SnapshotStatus.DELETING
                snapshot.save(update_fields=["status"])
                agent_client.send_operation(
                    vm.node, OperationType.DELETE_SNAPSHOT, resource_id=str(vm.uuid),
                    payload={"snapshot_id": snapshot.agent_snapshot_id, "snapshot_uuid": str(snapshot.uuid)},
                )
        snapshot.delete()
        transition(job, JobStatus.SUCCESS, message="Snapshot deleted")
    except Exception as exc:
        # The snapshot artifact itself is unaffected by a failed delete
        # *attempt* -- restore whatever status let this attempt start
        # (READY or, retrying a cleanup, ERROR) rather than ERROR
        # unconditionally, so the snapshot isn't left permanently stuck:
        # delete_snapshot only allows READY/ERROR through in the first
        # place, so anything else here would be a dead end.
        snapshot.status = status_before_attempt
        snapshot.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def rollback_snapshot_task(self, job_id: int, snapshot_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    snapshot = Snapshot.objects.select_related("vm", "vm__node").get(pk=snapshot_id)
    vm = snapshot.vm
    try:
        # Rollback touches both disk state and the running domain -- hold
        # both locks so it can never race a lifecycle op or another
        # storage op (section 20).
        with lifecycle_lock(vm), storage_lock(vm):
            with job_run(job, f"Rolling back to {snapshot.name}"):
                snapshot.status = SnapshotStatus.ROLLING_BACK
                snapshot.save(update_fields=["status"])
                agent_client.send_operation(
                    vm.node, OperationType.ROLLBACK_SNAPSHOT, resource_id=str(vm.uuid),
                    payload={"snapshot_id": snapshot.agent_snapshot_id, "snapshot_uuid": str(snapshot.uuid)},
                )
                snapshot.status = SnapshotStatus.READY
                snapshot.save(update_fields=["status"])
        transition(job, JobStatus.SUCCESS, message="Rolled back")
        _emit(vm, "VM_SNAPSHOT_ROLLED_BACK", snapshot_name=snapshot.name)
    except Exception as exc:
        # As with a failed restore_backup (apps.backups.tasks): the
        # snapshot itself -- its underlying storage/libvirt state -- is
        # unaffected by a failed *rollback attempt*, so it stays READY
        # rather than ERROR. Without this, a single transient failure
        # (agent timeout, a momentary lock conflict) would permanently
        # brick an otherwise-good snapshot: both delete_snapshot and
        # rollback_snapshot require READY, so ERROR here would leave it
        # with no way to ever be retried, rolled back to, or removed
        # short of direct DB access.
        snapshot.status = SnapshotStatus.READY
        snapshot.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


def _emit(vm, event_type: str, **metadata) -> None:
    from apps.events.services import emit_event

    emit_event(type=event_type, severity="INFO", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization, metadata=metadata)
