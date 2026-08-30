"""
BackupSchedule had no test coverage at all before this file, which is
exactly how two real bugs slipped in undetected:

1. BackupScheduleSerializer.validate_cron_expression only checked that a
   cron_expression had 5 whitespace-separated fields, never that each
   field was actually a valid cron value. `_sync_periodic_task` then fed
   those fields straight into `CrontabSchedule.objects.get_or_create(...)`
   -- which, unlike `full_clean()`, does not run the model's own field
   validators. A schedule with e.g. `"99 25 abc def ghi"` was accepted
   with a 201 and silently created a CrontabSchedule Celery Beat could
   never actually evaluate.

2. `apps.backups.services.update_schedule_enabled` -- written specifically
   to keep a schedule's linked PeriodicTask in sync -- was never actually
   called from anywhere. BackupScheduleViewSet had no `perform_update`
   override, so PATCH/PUT fell through to DRF's default
   `serializer.save()`, which updates the BackupSchedule row directly and
   never touches the PeriodicTask/CrontabSchedule at all. Disabling a
   schedule (`PATCH {"enabled": false}`) looked like it worked -- the row
   said so -- while Celery Beat kept firing it on the original crontab
   forever. Changing `cron_expression` had the same silent-drift problem.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.backups.models import BackupTarget
from apps.organizations.models import Membership
from apps.virtual_machines.models import VirtualMachine

pytestmark = pytest.mark.django_db


@pytest.fixture
def target(organization):
    return BackupTarget.objects.create(organization=organization, name="local-backups", type="LOCAL", config={"path": "/backups"})


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="STOPPED")


# --- serializer-level cron validation ---------------------------------


@pytest.mark.parametrize(
    "cron_expression",
    [
        "99 * * * *",  # minute out of range
        "* 25 * * *",  # hour out of range
        "* * 32 * *",  # day-of-month out of range
        "* * * 13 *",  # month out of range
        "* * * * abc",  # non-numeric, non-name day-of-week
        "* * * *",  # only 4 fields
    ],
)
def test_invalid_cron_expression_is_rejected_at_the_serializer(cron_expression):
    from apps.backups.serializers import BackupScheduleSerializer

    serializer = BackupScheduleSerializer(data={"cron_expression": cron_expression}, partial=True)
    assert not serializer.is_valid()
    assert "cron_expression" in serializer.errors


@pytest.mark.parametrize("cron_expression", ["0 3 * * *", "*/15 * * * *", "0 0 1 1 *", "0 9-17 * * mon-fri"])
def test_valid_cron_expressions_are_accepted(cron_expression):
    from apps.backups.serializers import BackupScheduleSerializer

    serializer = BackupScheduleSerializer(data={"cron_expression": cron_expression}, partial=True)
    serializer.is_valid()
    assert "cron_expression" not in serializer.errors


# --- service-level PeriodicTask sync -----------------------------------


def test_update_schedule_changes_the_linked_crontab(organization, vm, target):
    from apps.backups.services import create_schedule, update_schedule

    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")
    original_task_id = schedule.periodic_task_id

    updated = update_schedule(schedule, cron_expression="30 4 * * *")

    assert updated.periodic_task_id == original_task_id  # same PeriodicTask, re-pointed -- not orphaned
    updated.periodic_task.refresh_from_db()
    assert updated.periodic_task.crontab.minute == "30"
    assert updated.periodic_task.crontab.hour == "4"


def test_update_schedule_disabling_it_actually_disables_the_periodic_task(organization, vm, target):
    from apps.backups.services import create_schedule, update_schedule

    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")
    assert schedule.periodic_task.enabled is True

    updated = update_schedule(schedule, enabled=False)

    updated.periodic_task.refresh_from_db()
    assert updated.periodic_task.enabled is False


def test_update_schedule_leaves_the_periodic_task_alone_for_unrelated_fields(organization, vm, target):
    """retention_days doesn't affect when/whether Celery Beat fires the
    task (run_scheduled_backup reads it fresh from the model at trigger
    time), so no PeriodicTask write should happen for it."""
    from apps.backups.services import create_schedule, update_schedule

    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")

    with patch("django_celery_beat.models.PeriodicTask.save") as mock_save:
        update_schedule(schedule, retention_days=90)
        mock_save.assert_not_called()

    schedule.refresh_from_db()
    assert schedule.retention_days == 90


# --- end-to-end through the API -----------------------------------------


def test_patching_enabled_through_the_api_disables_the_periodic_task(user, organization, vm, target, grant_permission):
    from apps.backups.services import create_schedule

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.create")
    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(f"/api/v1/backup-schedules/{schedule.uuid}/", {"enabled": False}, format="json")

    assert response.status_code == 200
    schedule.periodic_task.refresh_from_db()
    assert schedule.periodic_task.enabled is False


def test_patching_cron_expression_through_the_api_updates_the_periodic_task(user, organization, vm, target, grant_permission):
    from apps.backups.services import create_schedule

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.create")
    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(f"/api/v1/backup-schedules/{schedule.uuid}/", {"cron_expression": "0 0 * * 0"}, format="json")

    assert response.status_code == 200
    schedule.periodic_task.refresh_from_db()
    assert schedule.periodic_task.crontab.hour == "0"
    assert schedule.periodic_task.crontab.day_of_week == "0"


def test_patching_an_invalid_cron_expression_through_the_api_is_rejected(user, organization, vm, target, grant_permission):
    from apps.backups.services import create_schedule

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.create")
    schedule = create_schedule(organization=organization, vm=vm, target=target, backup_type="FULL", cron_expression="0 3 * * *")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(f"/api/v1/backup-schedules/{schedule.uuid}/", {"cron_expression": "99 * * * *"}, format="json")

    assert response.status_code == 400
    schedule.periodic_task.refresh_from_db()
    assert schedule.periodic_task.crontab.minute == "0"  # unchanged
