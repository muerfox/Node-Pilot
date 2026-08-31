"""
apps.snapshots had zero test coverage despite having real business logic
(services.py + tasks.py) and a destructive rollback path guarded by two
locks. Tracing it surfaced the same class of bug already fixed once in
apps.backups.tasks.restore_backup_task: on a failed rollback or delete
*attempt*, the snapshot itself was marked ERROR -- but the snapshot
artifact is unaffected by the attempt failing, only the attempt is. Since
both delete_snapshot and rollback_snapshot required status == READY,
ERROR was a dead end: a single transient failure (agent timeout, a lock
conflict) would permanently brick an otherwise-good snapshot, with no
way to retry, roll back to it again, or even delete it.
"""
from __future__ import annotations

import pytest

from apps.common.exceptions import InvalidStateTransition
from apps.jobs.models import JobStatus
from apps.snapshots.models import Snapshot, SnapshotStatus
from apps.snapshots.tasks import create_snapshot_task, delete_snapshot_task, rollback_snapshot_task
from apps.storage.models import StoragePool, StorageType
from apps.virtual_machines.models import VirtualMachine, VMDisk

pytestmark = pytest.mark.django_db


@pytest.fixture
def snapshot_capable_storage(node):
    return StoragePool.objects.create(node=node, name="zfs-pool", type=StorageType.ZFS, path="tank/vms")


@pytest.fixture
def vm(organization, project, node, snapshot_capable_storage):
    vm = VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="RUNNING")
    VMDisk.objects.create(vm=vm, storage=snapshot_capable_storage, name="root", size_bytes=10 * 1024**3, bootable=True, volume_id="tank/vms/root")
    return vm


@pytest.fixture
def snapshot(vm):
    return Snapshot.objects.create(vm=vm, name="pre-upgrade", status=SnapshotStatus.READY, agent_snapshot_id="snap-1")


def _fake_agent(monkeypatch, *, fail=False, response=None):
    import apps.snapshots.tasks as tasks_module

    calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append((operation.value, payload))
        if fail:
            raise RuntimeError("agent unreachable")
        return response or {}

    monkeypatch.setattr(tasks_module.agent_client, "send_operation", fake_send_operation)
    return calls


# --- create -----------------------------------------------------------


def test_create_snapshot_rejects_a_vm_with_no_snapshot_capable_disks(organization, project, node, user):
    from apps.snapshots import services

    unsupported_storage = StoragePool.objects.create(node=node, name="lvm-pool", type=StorageType.LVM, path="/dev/vg0")
    vm = VirtualMachine.objects.create(organization=organization, project=project, node=node, name="no-snap", status="RUNNING")
    VMDisk.objects.create(vm=vm, storage=unsupported_storage, name="root", size_bytes=10 * 1024**3, bootable=True)

    with pytest.raises(Exception):
        services.create_snapshot(vm, name="x", description="", requested_by=user)


def test_create_snapshot_task_succeeds(vm, user, monkeypatch):
    from apps.snapshots import services

    calls = _fake_agent(monkeypatch, response={"snapshot_id": "snap-99", "size_bytes": 512})
    job = services.create_snapshot(vm, name="pre-upgrade", description="", requested_by=user)
    snapshot = Snapshot.objects.get(vm=vm, name="pre-upgrade")

    create_snapshot_task(job.pk, snapshot.pk)

    snapshot.refresh_from_db()
    job.refresh_from_db()
    assert snapshot.status == SnapshotStatus.READY
    assert snapshot.agent_snapshot_id == "snap-99"
    assert job.status == JobStatus.SUCCESS
    assert calls == [("CREATE_SNAPSHOT", {"snapshot_uuid": str(snapshot.uuid), "name": "pre-upgrade"})]


def test_create_snapshot_task_failure_leaves_it_in_error(vm, user, monkeypatch):
    from apps.snapshots import services

    _fake_agent(monkeypatch, fail=True)
    job = services.create_snapshot(vm, name="pre-upgrade", description="", requested_by=user)
    snapshot = Snapshot.objects.get(vm=vm, name="pre-upgrade")

    with pytest.raises(RuntimeError):
        create_snapshot_task(job.pk, snapshot.pk)

    snapshot.refresh_from_db()
    # Correct as-is: a snapshot that never finished being created has no
    # valid underlying artifact to be READY about. It must still be
    # cleanable, though -- see test_delete_snapshot_allows_cleaning_up_an_error_snapshot.
    assert snapshot.status == SnapshotStatus.ERROR


# --- rollback: the actual bug -------------------------------------------


def test_rollback_success_leaves_the_snapshot_ready(snapshot, user, monkeypatch):
    from apps.snapshots import services

    _fake_agent(monkeypatch)
    job = services.rollback_snapshot(snapshot, user)
    rollback_snapshot_task(job.pk, snapshot.pk)

    snapshot.refresh_from_db()
    job.refresh_from_db()
    assert snapshot.status == SnapshotStatus.READY
    assert job.status == JobStatus.SUCCESS


def test_a_failed_rollback_attempt_does_not_brick_the_snapshot(snapshot, user, monkeypatch):
    """The actual regression: a transient failure during rollback used
    to leave the snapshot at ERROR, and since both delete_snapshot and
    rollback_snapshot required READY, that was permanent -- no retry, no
    delete, nothing. The snapshot itself is unaffected by a failed
    rollback *attempt*, so it must come back READY."""
    from apps.snapshots import services

    _fake_agent(monkeypatch, fail=True)
    job = services.rollback_snapshot(snapshot, user)

    with pytest.raises(RuntimeError):
        rollback_snapshot_task(job.pk, snapshot.pk)

    snapshot.refresh_from_db()
    assert snapshot.status == SnapshotStatus.READY  # not ERROR

    # And it's provably not bricked: a second rollback attempt is allowed.
    retry_job = services.rollback_snapshot(snapshot, user)
    assert retry_job is not None


# --- delete --------------------------------------------------------------


def test_delete_snapshot_success_removes_the_row(snapshot, user, monkeypatch):
    from apps.snapshots import services

    _fake_agent(monkeypatch)
    job = services.delete_snapshot(snapshot, user)
    delete_snapshot_task(job.pk, snapshot.pk)

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert not Snapshot.objects.filter(pk=snapshot.pk).exists()


def test_a_failed_delete_attempt_reverts_to_the_status_it_had_before(snapshot, user, monkeypatch):
    from apps.snapshots import services

    _fake_agent(monkeypatch, fail=True)
    job = services.delete_snapshot(snapshot, user)  # snapshot starts READY

    with pytest.raises(RuntimeError):
        delete_snapshot_task(job.pk, snapshot.pk)

    snapshot.refresh_from_db()
    assert snapshot.status == SnapshotStatus.READY  # restored, not stuck at ERROR
    assert Snapshot.objects.filter(pk=snapshot.pk).exists()


def test_delete_snapshot_allows_cleaning_up_an_error_snapshot(vm, user):
    from apps.snapshots import services

    broken = Snapshot.objects.create(vm=vm, name="broken", status=SnapshotStatus.ERROR)
    job = services.delete_snapshot(broken, user)  # must not raise InvalidStateTransition
    assert job is not None


def test_delete_snapshot_rejects_a_snapshot_mid_operation(vm, user):
    from apps.snapshots import services

    creating = Snapshot.objects.create(vm=vm, name="in-progress", status=SnapshotStatus.CREATING)
    with pytest.raises(InvalidStateTransition):
        services.delete_snapshot(creating, user)
