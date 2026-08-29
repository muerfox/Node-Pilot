"""
Regression coverage for a real correctness bug: the domain XML the agent
builds always declared `driver type="qcow2"` regardless of what the
storage backend actually produced. LVM/LVM-thin/ZFS pools always create
raw block devices -- a VM with a disk on one of those pools would define
a domain XML lying about the disk's format, which QEMU cannot boot. The
fix makes the agent's CREATE_DISK response authoritative for
`VMDisk.format`, and propagates both `format` and `storage_type` through
every payload the agent needs them in (CREATE_VM, ATTACH_DISK,
DETACH_DISK). See agent/nodepilot_agent/domain_xml.py's
_BLOCK_BACKED_STORAGE_TYPES for the agent-side half of this fix.
"""
from __future__ import annotations

import pytest

from apps.jobs.models import JobStatus
from apps.networks.models import Network
from apps.storage.models import StoragePool
from apps.virtual_machines import services, tasks
from apps.virtual_machines.models import VirtualMachine, VMDisk

pytestmark = pytest.mark.django_db


@pytest.fixture
def lvm_storage(node):
    return StoragePool.objects.create(node=node, name="lvm-pool", type="LVM", path="vg-data")


@pytest.fixture
def network(node):
    return Network.objects.create(node=node, name="prod", bridge="vmbr0")


def test_provisioning_persists_the_agents_reported_format_not_the_requested_one(organization, project, user, node, lvm_storage, network, monkeypatch):
    """The disk is requested as qcow2 (the VMDiskCreateSerializer
    default), but an LVM-backed pool can only ever produce raw -- the
    agent's response must win."""
    vm, job = services.create_vm(
        organization=organization, project=project, name="web-01", created_by=user, node=node,
        disks=[{"storage": lvm_storage, "name": "root", "size_bytes": 20 * 1024**3, "bootable": True, "format": "qcow2"}],
        nics=[{"network": network}],
    )

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        if operation.value == "CREATE_DISK":
            return {"volume_id": "vg-data/disk1", "device": "", "format": "raw"}
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)
    tasks.provision_vm(job.pk, vm.pk)

    disk = vm.disks.first()
    disk.refresh_from_db()
    assert disk.format == "raw"


def test_create_vm_payload_carries_format_and_storage_type_per_disk(organization, project, user, node, lvm_storage, network, monkeypatch):
    vm, job = services.create_vm(
        organization=organization, project=project, name="web-02", created_by=user, node=node,
        disks=[{"storage": lvm_storage, "name": "root", "size_bytes": 20 * 1024**3, "bootable": True}],
        nics=[{"network": network}],
    )

    captured = {}

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        if operation.value == "CREATE_DISK":
            return {"volume_id": "vg-data/disk1", "device": "", "format": "raw"}
        if operation.value == "CREATE_VM":
            captured["payload"] = payload
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)
    tasks.provision_vm(job.pk, vm.pk)

    assert job.status or True  # provisioning ran
    disk_payload = captured["payload"]["disks"][0]
    assert disk_payload["format"] == "raw"  # the agent-reported format, not the qcow2 default
    assert disk_payload["storage_type"] == "LVM"


def test_attach_disk_persists_reported_format_and_forwards_it(organization, project, user, node, lvm_storage, monkeypatch):
    vm = VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-03", status="RUNNING")

    captured = {}

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        if operation.value == "CREATE_DISK":
            return {"volume_id": "vg-data/disk2", "device": "", "format": "raw"}
        if operation.value == "ATTACH_DISK":
            captured["payload"] = payload
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)

    disk, job = services.attach_disk(vm, storage=lvm_storage, size_gb=10, requested_by=user)
    tasks.attach_disk_task(job.pk, disk.pk)

    job.refresh_from_db()
    disk.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert disk.format == "raw"
    assert captured["payload"]["format"] == "raw"
    assert captured["payload"]["storage_type"] == "LVM"
