"""
End-to-end test of the VM creation service + provisioning task, with the
agent RPC layer mocked out (apps.nodes.agent_client.send_operation) --
these tests never touch a real hypervisor, matching rule 55: "use mocks
for libvirt/QEMU in normal CI."

The Celery task is invoked directly as a plain function rather than via
`.delay()`, since `services.create_vm` schedules it through
`transaction.on_commit`, which never fires inside pytest-django's
transaction-rollback `db` fixture. Calling `tasks.provision_vm(...)`
directly exercises exactly the same code the Celery worker would run.
"""
from __future__ import annotations

import pytest

from apps.common.exceptions import AgentOperationFailed
from apps.jobs.models import JobStatus, JobType
from apps.networks.models import Network
from apps.storage.models import StoragePool
from apps.virtual_machines import services, tasks
from apps.virtual_machines.models import ProvisioningState, VMStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/var/lib/nodepilot/pools/local")


@pytest.fixture
def network(node):
    return Network.objects.create(node=node, name="prod", bridge="vmbr0")


def _create(organization, project, user, node, storage, network, **overrides):
    kwargs = dict(
        organization=organization, project=project, name="web-01", created_by=user, node=node,
        cpu_count=2, memory_mb=2048,
        disks=[{"storage": storage, "name": "root", "size_bytes": 10 * 1024**3, "bootable": True}],
        nics=[{"network": network}],
        autostart=True,
    )
    kwargs.update(overrides)
    return services.create_vm(**kwargs)


def test_create_vm_sets_up_disks_and_nics(organization, project, user, node, storage, network):
    vm, job = _create(organization, project, user, node, storage, network)

    assert vm.status == VMStatus.CREATING
    assert vm.provisioning_state == ProvisioningState.REQUESTED
    assert job.type == JobType.VM_CREATE
    assert job.status == JobStatus.QUEUED

    assert vm.disks.count() == 1
    disk = vm.disks.first()
    assert disk.size_bytes == 10 * 1024**3
    assert disk.bootable is True

    assert vm.nics.count() == 1
    nic = vm.nics.first()
    assert nic.mac_address.startswith("52:54:00")


def test_create_vm_persists_and_forwards_a_nic_rate_limit(organization, project, user, node, storage, network, monkeypatch):
    """VMNic.rate_limit_mbps used to have no path to actually get set at
    all (create_vm's nic-creation loop dropped it even if a caller
    passed it), and CREATE_VM's domain payload never included it either."""
    vm, job = _create(organization, project, user, node, storage, network, nics=[{"network": network, "rate_limit_mbps": 100}])

    nic = vm.nics.get()
    assert nic.rate_limit_mbps == 100

    calls = []
    monkeypatch.setattr(tasks.agent_client, "send_operation", lambda target_node, operation, resource_id, payload=None, timeout=None: calls.append((operation.value, payload)) or ({"volume_id": "vol-1", "device": "vda"} if operation.value == "CREATE_DISK" else {}))

    tasks.provision_vm(job.pk, vm.pk)

    create_vm_payload = next(payload for name, payload in calls if name == "CREATE_VM")
    assert create_vm_payload["nics"][0]["rate_limit_mbps"] == 100


def test_provision_vm_happy_path(organization, project, user, node, storage, network, monkeypatch):
    vm, job = _create(organization, project, user, node, storage, network)

    calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append(operation)
        if operation.value == "CREATE_DISK":
            return {"volume_id": "vol-1", "device": "vda"}
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)

    tasks.provision_vm(job.pk, vm.pk)

    job.refresh_from_db()
    vm.refresh_from_db()

    assert job.status == JobStatus.SUCCESS
    assert vm.status == VMStatus.RUNNING
    assert vm.provisioning_state == ProvisioningState.READY

    disk = vm.disks.first()
    assert disk.volume_id == "vol-1"
    assert disk.device == "vda"

    op_names = [op.value for op in calls]
    assert "CREATE_DISK" in op_names
    assert "CREATE_VM" in op_names
    assert "START_VM" in op_names


def test_provision_vm_failure_marks_error_and_cleans_up(organization, project, user, node, storage, network, monkeypatch):
    vm, job = _create(organization, project, user, node, storage, network)

    cleanup_calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        if operation.value == "CREATE_DISK":
            raise AgentOperationFailed("disk creation exploded")
        cleanup_calls.append(operation)
        return {}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)

    with pytest.raises(AgentOperationFailed):
        tasks.provision_vm(job.pk, vm.pk)

    job.refresh_from_db()
    vm.refresh_from_db()

    assert job.status == JobStatus.FAILED
    assert vm.status == VMStatus.ERROR
    assert vm.provisioning_state == ProvisioningState.ERROR
    assert "disk creation exploded" in vm.last_error
    # No disk ever got a volume_id, so cleanup had nothing to tear down.
    assert cleanup_calls == []


def test_start_vm_rejects_already_running_vm(organization, project, user, node, storage, network, monkeypatch):
    from apps.common.exceptions import InvalidStateTransition

    vm, _ = _create(organization, project, user, node, storage, network)
    vm.status = VMStatus.RUNNING
    vm.save(update_fields=["status"])

    with pytest.raises(InvalidStateTransition):
        services.start_vm(vm, user)
