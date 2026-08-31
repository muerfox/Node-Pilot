"""
apps.virtual_machines.scheduler had zero test coverage before this file.
Tracing it surfaced a real overcommit race: node.storage_available_gb is
only as fresh as the node's last heartbeat, but a VM's disk is created
(consuming real host storage) as soon as its VMDisk row exists --
regardless of whether the VM has ever been started, unlike memory/CPU.
Two VMs scheduled to the same node within one heartbeat interval could
each individually pass the capacity check and, together, overcommit real
storage. _pending_storage_gb closes that by subtracting disks created
since the node's last heartbeat from its reported free space.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.storage.models import StoragePool
from apps.virtual_machines.models import VirtualMachine, VMDisk, VMStatus
from apps.virtual_machines.scheduler import CapacityWeightedScheduler, NoSchedulableNode, SchedulingRequest

pytestmark = pytest.mark.django_db


@pytest.fixture
def scheduler():
    return CapacityWeightedScheduler()


def _make_node(organization, **overrides):
    from apps.nodes.models import Node

    defaults = dict(
        organization=organization, name="node", hostname=f"node-{overrides.get('name', 'x')}.local",
        cpu_threads=8, memory_total_mb=32768, memory_available_mb=16384,
        storage_total_gb=1000, storage_available_gb=500, last_seen=timezone.now(),
    )
    defaults.update(overrides)
    return Node.objects.create(**defaults)


def test_picks_the_only_online_schedulable_node(organization, scheduler):
    node = _make_node(organization, name="a")
    picked = scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=2, memory_mb=4096, disk_gb=50))
    assert picked == node


def test_excludes_nodes_that_are_offline(organization, scheduler):
    _make_node(organization, name="a", last_seen=None)  # never seen -> OFFLINE
    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=10))


def test_excludes_nodes_in_maintenance(organization, scheduler):
    from apps.nodes.models import NodeAdminState

    _make_node(organization, name="a", admin_state=NodeAdminState.MAINTENANCE)
    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=10))


def test_excludes_a_node_without_enough_free_memory(organization, scheduler):
    _make_node(organization, name="a", memory_available_mb=1024)
    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=4096, disk_gb=10))


def test_excludes_a_node_without_enough_free_storage(organization, scheduler):
    _make_node(organization, name="a", storage_available_gb=20)
    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=50))


def test_prefers_the_node_with_more_balanced_spare_capacity(organization, scheduler):
    tight = _make_node(organization, name="tight", memory_available_mb=4096, memory_total_mb=8192)
    roomy = _make_node(organization, name="roomy", memory_available_mb=28672, memory_total_mb=32768)
    picked = scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=2048, disk_gb=10))
    assert picked == roomy
    assert picked != tight


def test_cpu_overcommit_only_counts_running_vms(organization, project, scheduler):
    """A stopped VM consumes no real CPU cycles -- the overcommit budget
    is about active load, not how many VMs merely exist. Filling a node
    with stopped VMs must not make it look unschedulable."""
    node = _make_node(organization, name="a", cpu_threads=4)  # max_vcpu = 4 * 4 = 16
    VirtualMachine.objects.create(organization=organization, project=project, node=node, name="stopped-1", status=VMStatus.STOPPED, cpu_count=8)
    VirtualMachine.objects.create(organization=organization, project=project, node=node, name="running-1", status=VMStatus.RUNNING, cpu_count=8)

    # 8 vCPU already running -> 8 free out of 16; a 6-vCPU request still fits.
    picked = scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=6, memory_mb=1024, disk_gb=10))
    assert picked == node


def test_cpu_overcommit_rejects_when_running_vms_exceed_the_budget(organization, project, scheduler):
    node = _make_node(organization, name="a", cpu_threads=4)  # max_vcpu = 16
    VirtualMachine.objects.create(organization=organization, project=project, node=node, name="running-1", status=VMStatus.RUNNING, cpu_count=14)

    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=4, memory_mb=1024, disk_gb=10))


# --- storage overcommit race ---------------------------------------------


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status=VMStatus.STOPPED)


def _give_ample_cpu_and_memory(node) -> None:
    """The conftest `node` fixture defaults cpu_threads/memory_*/
    storage_total_gb to 0 -- fine for tests that don't care, but these
    storage-race tests need memory/CPU to never be the binding
    constraint so the assertions actually isolate the storage logic."""
    node.cpu_threads = 8
    node.memory_total_mb = 32768
    node.memory_available_mb = 16384
    node.storage_total_gb = 1000
    node.save(update_fields=["cpu_threads", "memory_total_mb", "memory_available_mb", "storage_total_gb"])


def test_a_disk_created_since_the_last_heartbeat_reduces_apparent_free_storage(organization, node, storage, vm, scheduler):
    _give_ample_cpu_and_memory(node)
    node.storage_available_gb = 100
    node.last_seen = timezone.now()
    node.save(update_fields=["storage_available_gb", "last_seen"])

    # Created "now" -- after last_seen -- simulating a disk provisioned
    # moments ago that the next heartbeat hasn't reported yet.
    VMDisk.objects.create(vm=vm, storage=storage, name="root", size_bytes=80 * 1024**3, bootable=True)

    # 100GB reported free, but 80GB is already spoken for -> only ~20GB
    # really available, not enough for a second 50GB disk.
    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=50))


def test_a_disk_created_before_the_last_heartbeat_is_not_double_counted(organization, node, storage, vm, scheduler):
    """That disk's space is already baked into storage_available_gb (the
    host measured it directly) -- subtracting it again would
    under-schedule the node for no reason."""
    _give_ample_cpu_and_memory(node)
    disk = VMDisk.objects.create(vm=vm, storage=storage, name="root", size_bytes=80 * 1024**3, bootable=True)
    VMDisk.objects.filter(pk=disk.pk).update(created_at=timezone.now() - timedelta(hours=1))

    node.storage_available_gb = 100  # heartbeat already reflects the 80GB disk being gone
    node.last_seen = timezone.now()
    node.save(update_fields=["storage_available_gb", "last_seen"])

    picked = scheduler.select_node(SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=50))
    assert picked == node


def test_two_back_to_back_schedules_within_one_heartbeat_window_do_not_both_fit(organization, project, node, storage, scheduler):
    """The actual race this closes: schedule a VM (creating its disk),
    then immediately ask again before any heartbeat arrives -- the
    second request must see the first VM's disk as committed space."""
    _give_ample_cpu_and_memory(node)
    node.storage_available_gb = 100
    node.last_seen = timezone.now()
    node.save(update_fields=["storage_available_gb", "last_seen"])

    request = SchedulingRequest(organization_id=organization.pk, cpu_count=1, memory_mb=1024, disk_gb=60)
    picked = scheduler.select_node(request)
    assert picked == node

    vm = VirtualMachine.objects.create(organization=organization, project=project, node=node, name="first", status=VMStatus.STOPPED)
    VMDisk.objects.create(vm=vm, storage=storage, name="root", size_bytes=60 * 1024**3, bootable=True)

    with pytest.raises(NoSchedulableNode):
        scheduler.select_node(request)
