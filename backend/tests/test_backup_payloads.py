"""
Regression coverage for a real bug: CREATE_BACKUP/RESTORE_BACKUP payloads
never included which disk to actually operate on (`volume_id`), so both
the agent's create_backup and restore_backup would always raise
StorageOperationError -- the "LOCAL/NFS backups work end-to-end" claim
in earlier docs was wrong. See apps.backups.tasks._primary_disk.
"""
from __future__ import annotations

import pytest

from apps.backups.models import Backup, BackupStatus, BackupTarget
from apps.backups.tasks import create_backup_task, restore_backup_task
from apps.jobs.models import Job, JobStatus, JobType
from apps.jobs.services import create_job
from apps.storage.models import StoragePool
from apps.virtual_machines.models import VirtualMachine, VMDisk

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def target(organization):
    return BackupTarget.objects.create(organization=organization, name="local-backups", type="LOCAL", config={"path": "/backups"})


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="STOPPED")


@pytest.fixture
def boot_disk(vm, storage):
    return VMDisk.objects.create(vm=vm, storage=storage, name="root", size_bytes=10 * 1024**3, bootable=True, volume_id="/pools/local/root.qcow2", format="qcow2")


def _job_for(vm, job_type):
    return create_job(type=job_type, resource_type="VirtualMachine", organization=vm.organization, node=vm.node, created_by=None)


def test_create_backup_payload_includes_the_boot_disks_volume_id(vm, boot_disk, target, monkeypatch):
    backup = Backup.objects.create(vm=vm, target=target, type="FULL", status=BackupStatus.PENDING)
    job = _job_for(vm, JobType.BACKUP_CREATE)

    captured = {}

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        captured["payload"] = payload
        return {"backup_ref": "/backups/x.qcow2", "size_bytes": 123, "checksum": "abc"}

    monkeypatch.setattr("apps.backups.tasks.agent_client.send_operation", fake_send_operation)
    create_backup_task(job.pk, backup.pk)

    assert captured["payload"]["volume_id"] == boot_disk.volume_id
    job.refresh_from_db()
    backup.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert backup.status == BackupStatus.COMPLETED


def test_create_backup_fails_cleanly_when_vm_has_no_disks(organization, project, node, target):
    vm = VirtualMachine.objects.create(organization=organization, project=project, node=node, name="no-disks", status="STOPPED")
    backup = Backup.objects.create(vm=vm, target=target, type="FULL", status=BackupStatus.PENDING)
    job = _job_for(vm, JobType.BACKUP_CREATE)

    with pytest.raises(Exception):
        create_backup_task(job.pk, backup.pk)

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED


def test_restore_backup_payload_includes_destination_volume_id_and_format(vm, boot_disk, target, monkeypatch):
    backup = Backup.objects.create(vm=vm, target=target, type="FULL", status=BackupStatus.COMPLETED, agent_backup_ref="/backups/x.qcow2")
    job = _job_for(vm, JobType.BACKUP_RESTORE)

    captured = {}

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        captured["payload"] = payload
        return {}

    monkeypatch.setattr("apps.backups.tasks.agent_client.send_operation", fake_send_operation)
    restore_backup_task(job.pk, backup.pk)

    assert captured["payload"]["volume_id"] == boot_disk.volume_id
    assert captured["payload"]["format"] == boot_disk.format
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
