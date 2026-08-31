"""Covers the disk/NIC attach/detach/resize services + tasks added
alongside the frontend's Disks/Network VM-detail tabs -- same
direct-task-call pattern as test_vm_service.py (see its module
docstring for why)."""
from __future__ import annotations

import pytest

from apps.common.exceptions import InvalidStateTransition
from apps.jobs.models import JobStatus
from apps.networks.models import Network
from apps.storage.models import StoragePool
from apps.virtual_machines import services, tasks
from apps.virtual_machines.models import VirtualMachine, VMDisk

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def network(node):
    return Network.objects.create(node=node, name="prod", bridge="vmbr0", vlan_id=120)


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="RUNNING")


@pytest.fixture
def boot_disk(vm, storage):
    return VMDisk.objects.create(vm=vm, storage=storage, name="root", size_bytes=10 * 1024**3, bootable=True, volume_id="/pools/local/root.qcow2")


def _fake_agent(monkeypatch, responses=None):
    calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append((operation.value, payload))
        if responses and operation.value in responses:
            return responses[operation.value]
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)
    return calls


def test_attach_disk_creates_row_and_job(vm, storage, user, monkeypatch):
    _fake_agent(monkeypatch, {"CREATE_DISK": {"volume_id": "/pools/local/disk2.qcow2", "device": "vdb"}})

    disk, job = services.attach_disk(vm, storage=storage, size_gb=20, bus="VIRTIO", requested_by=user)
    assert disk.size_bytes == 20 * 1024**3
    assert vm.disks.count() == 1  # not yet attached by the task

    tasks.attach_disk_task(job.pk, disk.pk)

    disk.refresh_from_db()
    job.refresh_from_db()
    assert disk.volume_id == "/pools/local/disk2.qcow2"
    assert disk.device == "vdb"
    assert job.status == JobStatus.SUCCESS


def test_detach_boot_disk_is_rejected(vm, boot_disk, user):
    with pytest.raises(InvalidStateTransition):
        services.detach_disk(vm, boot_disk, user)


def test_detach_non_boot_disk_removes_it(vm, storage, user, monkeypatch):
    calls = _fake_agent(monkeypatch)
    extra_disk = VMDisk.objects.create(vm=vm, storage=storage, name="data", size_bytes=5 * 1024**3, bootable=False, volume_id="/pools/local/data.qcow2")

    job = services.detach_disk(vm, extra_disk, user)
    tasks.detach_disk_task(job.pk, extra_disk.pk)

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert not VMDisk.objects.filter(pk=extra_disk.pk).exists()
    op_names = [name for name, _ in calls]
    assert "DETACH_DISK" in op_names
    assert "DELETE_DISK" in op_names


def test_resize_disk_rejects_shrink(vm, boot_disk, user):
    with pytest.raises(InvalidStateTransition):
        services.resize_disk(vm, boot_disk, new_size_gb=5, requested_by=user)  # boot_disk is already 10GB


def test_resize_disk_grows_and_updates_size(vm, boot_disk, user, monkeypatch):
    _fake_agent(monkeypatch)
    job = services.resize_disk(vm, boot_disk, new_size_gb=40, requested_by=user)
    tasks.resize_disk_task(job.pk, boot_disk.pk, 40 * 1024**3)

    boot_disk.refresh_from_db()
    job.refresh_from_db()
    assert boot_disk.size_bytes == 40 * 1024**3
    assert job.status == JobStatus.SUCCESS


def test_attach_and_detach_nic(vm, network, user, monkeypatch):
    calls = _fake_agent(monkeypatch)
    nic, job = services.attach_nic(vm, network=network, requested_by=user)
    tasks.attach_nic_task(job.pk, nic.pk)

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert vm.nics.filter(pk=nic.pk).exists()

    detach_job = services.detach_nic(vm, nic, user)
    tasks.detach_nic_task(detach_job.pk, nic.pk)

    detach_job.refresh_from_db()
    assert detach_job.status == JobStatus.SUCCESS
    assert not vm.nics.filter(pk=nic.pk).exists()
    assert any(name == "ATTACH_NIC" for name, _ in calls)
    assert any(name == "DETACH_NIC" for name, _ in calls)
    # Regression: ATTACH_NIC/DETACH_NIC payloads used to omit `vlan`
    # entirely, so a NIC on a VLAN-tagged network attached to the raw
    # (untagged) bridge with no isolation from other networks sharing it.
    attach_payload = next(payload for name, payload in calls if name == "ATTACH_NIC")
    detach_payload = next(payload for name, payload in calls if name == "DETACH_NIC")
    assert attach_payload["vlan"] == 120
    assert detach_payload["vlan"] == 120
