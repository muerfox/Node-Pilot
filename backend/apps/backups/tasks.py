from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.backups.models import Backup, BackupSchedule, BackupStatus
from apps.common.exceptions import NodePilotAPIException
from apps.jobs.models import Job, JobStatus
from apps.jobs.services import job_run, transition
from apps.jobs.tasks import JobBoundTask
from apps.nodes import agent_client
from apps.nodes.protocol import OperationType
from apps.virtual_machines.locks import storage_lock


def _primary_disk(vm):
    """The disk a whole-VM backup/restore actually operates on: the
    bootable disk if one is marked, else the first by boot_index. (A
    real per-disk backup selection is a natural follow-up; today's
    Backup model is scoped to one VM, which in practice means its boot
    disk.)"""
    disk = vm.disks.select_related("storage").filter(bootable=True).order_by("boot_index").first()
    return disk or vm.disks.select_related("storage").order_by("boot_index").first()


@shared_task(bind=True, base=JobBoundTask)
def create_backup_task(self, job_id: int, backup_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    backup = Backup.objects.select_related("vm", "vm__node", "target").get(pk=backup_id)
    vm = backup.vm
    try:
        with storage_lock(vm):
            with job_run(job, f"Creating {backup.type.lower()} backup"):
                backup.status = BackupStatus.RUNNING
                backup.started_at = timezone.now()
                backup.save(update_fields=["status", "started_at"])

                disk = _primary_disk(vm)
                if disk is None:
                    raise NodePilotAPIException(f"VM {vm.name} has no disks to back up.", code_name="VM_HAS_NO_DISKS")

                data = agent_client.send_operation(
                    vm.node, OperationType.CREATE_BACKUP, resource_id=str(vm.uuid),
                    payload={
                        "backup_uuid": str(backup.uuid), "backup_type": backup.type, "target": backup.target.config,
                        "target_type": backup.target.type, "volume_id": disk.volume_id,
                    },
                    timeout=3600,
                )
                backup.agent_backup_ref = data.get("backup_ref", "")
                backup.size_bytes = data.get("size_bytes", 0)
                backup.checksum = data.get("checksum", "")
                backup.status = BackupStatus.COMPLETED
                backup.finished_at = timezone.now()
                backup.save(update_fields=["agent_backup_ref", "size_bytes", "checksum", "status", "finished_at"])

        transition(job, JobStatus.SUCCESS, message="Backup completed")
        _emit(vm, "BACKUP_COMPLETED", backup_uuid=str(backup.uuid))
    except Exception as exc:
        backup.status = BackupStatus.FAILED
        backup.finished_at = timezone.now()
        backup.save(update_fields=["status", "finished_at"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        _emit(vm, "BACKUP_FAILED", backup_uuid=str(backup.uuid), error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def restore_backup_task(self, job_id: int, backup_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    backup = Backup.objects.select_related("vm", "vm__node", "target").get(pk=backup_id)
    vm = backup.vm
    try:
        with storage_lock(vm):
            with job_run(job, "Restoring backup"):
                backup.status = BackupStatus.RESTORING
                backup.save(update_fields=["status"])

                disk = _primary_disk(vm)
                if disk is None:
                    raise NodePilotAPIException(f"VM {vm.name} has no disk to restore onto.", code_name="VM_HAS_NO_DISKS")

                agent_client.send_operation(
                    vm.node, OperationType.RESTORE_BACKUP, resource_id=str(vm.uuid),
                    payload={
                        "backup_ref": backup.agent_backup_ref, "target": backup.target.config, "target_type": backup.target.type,
                        "volume_id": disk.volume_id, "format": disk.format,
                    },
                    timeout=3600,
                )
                backup.status = BackupStatus.COMPLETED
                backup.save(update_fields=["status"])
        transition(job, JobStatus.SUCCESS, message="Restore completed")
    except Exception as exc:
        backup.status = BackupStatus.COMPLETED  # the backup artifact itself is unaffected by a failed restore
        backup.save(update_fields=["status"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(name="backups.run_scheduled_backup")
def run_scheduled_backup(schedule_id: int) -> None:
    schedule = BackupSchedule.objects.select_related("vm", "target", "organization").filter(pk=schedule_id, enabled=True).first()
    if schedule is None:
        return
    from datetime import timedelta

    from apps.backups.services import create_backup

    job = create_backup(schedule.vm, schedule.target, backup_type=schedule.backup_type, requested_by=None)
    Backup.objects.filter(uuid=job.resource_id).update(retention_expires_at=timezone.now() + timedelta(days=schedule.retention_days))


@shared_task(name="backups.apply_retention")
def apply_retention_task() -> int:
    from apps.backups.models import BackupTarget
    from apps.backups.services import apply_retention

    total = 0
    for target in BackupTarget.objects.filter(enabled=True):
        total += apply_retention(target)
    return total


def _emit(vm, event_type: str, **metadata) -> None:
    from apps.events.services import emit_event

    emit_event(type=event_type, severity="INFO" if event_type != "BACKUP_FAILED" else "CRITICAL", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization, metadata=metadata)
