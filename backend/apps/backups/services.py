from __future__ import annotations

import json

from django.db import transaction
from django.utils import timezone

from apps.backups.models import Backup, BackupSchedule, BackupStatus
from apps.common.exceptions import InvalidStateTransition, NodePilotAPIException, ResourceLocked
from apps.jobs.models import JobType
from apps.jobs.services import create_job
from apps.virtual_machines.locks import storage_lock


def create_backup(vm, target, *, backup_type: str, requested_by) -> "Job":
    lock = storage_lock(vm)
    if not lock.acquire(blocking=False):
        raise ResourceLocked(f"VM {vm.name} has a storage operation in progress.")
    lock.release()

    backup = Backup.objects.create(vm=vm, target=target, type=backup_type, status=BackupStatus.PENDING)
    job = create_job(type=JobType.BACKUP_CREATE, resource_type="Backup", resource_id=str(backup.uuid), organization=vm.organization, node=vm.node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue_create(job.pk, backup.pk))
    return job


def restore_backup(backup: Backup, requested_by) -> "Job":
    if backup.status != BackupStatus.COMPLETED:
        raise InvalidStateTransition(f"Cannot restore a backup in status {backup.status}")
    vm = backup.vm
    if vm.status != "STOPPED":
        raise NodePilotAPIException("The VM must be stopped before restoring a backup onto it.", code_name="VM_NOT_STOPPED", status_code=409)

    lock = storage_lock(vm)
    if not lock.acquire(blocking=False):
        raise ResourceLocked(f"VM {vm.name} has a storage operation in progress.")
    lock.release()

    job = create_job(type=JobType.BACKUP_RESTORE, resource_type="Backup", resource_id=str(backup.uuid), organization=vm.organization, node=vm.node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue_restore(job.pk, backup.pk))
    return job


def delete_backup(backup: Backup) -> None:
    backup.status = BackupStatus.DELETED
    backup.save(update_fields=["status"])


def _enqueue_create(job_id: int, backup_id: int) -> None:
    from apps.backups.tasks import create_backup_task

    create_backup_task.delay(job_id, backup_id)


def _enqueue_restore(job_id: int, backup_id: int) -> None:
    from apps.backups.tasks import restore_backup_task

    restore_backup_task.delay(job_id, backup_id)


def create_schedule(*, organization, vm, target, backup_type: str, cron_expression: str, timezone_name: str = "UTC", retention_days: int = 30) -> BackupSchedule:
    schedule = BackupSchedule.objects.create(
        organization=organization, vm=vm, target=target, backup_type=backup_type,
        cron_expression=cron_expression, timezone=timezone_name, retention_days=retention_days,
    )
    _sync_periodic_task(schedule)
    return schedule


def update_schedule(schedule: BackupSchedule, **fields) -> BackupSchedule:
    """Applies a partial update to `schedule` and keeps its linked Celery
    Beat PeriodicTask in sync. A plain `serializer.save()` would update
    the BackupSchedule row but silently leave the PeriodicTask (and its
    CrontabSchedule) exactly as `_sync_periodic_task` first created it --
    most dangerously for `enabled`, where PATCHing `enabled: false` would
    look like it worked (the DB row says so) while Celery Beat kept
    firing the schedule on its original crontab forever.
    """
    cron_or_tz_changed = ("cron_expression" in fields and fields["cron_expression"] != schedule.cron_expression) or (
        "timezone" in fields and fields["timezone"] != schedule.timezone
    )

    for field, value in fields.items():
        setattr(schedule, field, value)
    if fields:
        schedule.save(update_fields=list(fields))

    if schedule.periodic_task_id:
        task_update_fields = []

        if cron_or_tz_changed:
            from django_celery_beat.models import CrontabSchedule

            minute, hour, day_of_month, month_of_year, day_of_week = schedule.cron_expression.split()
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=minute, hour=hour, day_of_month=day_of_month, month_of_year=month_of_year, day_of_week=day_of_week,
                timezone=schedule.timezone,
            )
            schedule.periodic_task.crontab = crontab
            task_update_fields.append("crontab")

        if "enabled" in fields:
            schedule.periodic_task.enabled = schedule.enabled
            task_update_fields.append("enabled")

        if task_update_fields:
            schedule.periodic_task.save(update_fields=task_update_fields)

    return schedule


def delete_schedule(schedule: BackupSchedule) -> None:
    if schedule.periodic_task_id:
        schedule.periodic_task.delete()
    schedule.delete()


def _sync_periodic_task(schedule: BackupSchedule) -> None:
    """Wires the schedule to Celery Beat (section 27) via
    django_celery_beat's DatabaseScheduler, timezone-aware per schedule."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    minute, hour, day_of_month, month_of_year, day_of_week = schedule.cron_expression.split()
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=minute, hour=hour, day_of_month=day_of_month, month_of_year=month_of_year, day_of_week=day_of_week,
        timezone=schedule.timezone,
    )
    task = PeriodicTask.objects.create(
        crontab=crontab,
        name=f"backup-schedule-{schedule.uuid}",
        task="backups.run_scheduled_backup",
        args=json.dumps([schedule.pk]),
        enabled=schedule.enabled,
    )
    schedule.periodic_task = task
    schedule.save(update_fields=["periodic_task"])


def apply_retention(target) -> int:
    """Deletes (marks DELETED) completed backups on `target` whose
    schedule-derived retention window has passed. Called by the
    `backups.apply_retention` periodic task."""
    expired = Backup.objects.filter(target=target, status=BackupStatus.COMPLETED, retention_expires_at__lt=timezone.now())
    count = expired.count()
    for backup in expired:
        delete_backup(backup)
    return count
