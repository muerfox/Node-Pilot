"""
VM lifecycle service (sections 10, 18, 20, 25, 50). HTTP views never touch
libvirt or the agent directly (rule 4) -- they call into this module,
which creates a Job and hands the actual work to a Celery task
(apps.virtual_machines.tasks). Every mutating entry point here enforces
quota, RBAC (already checked by the view), and the appropriate Redis lock.
"""
from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import InvalidStateTransition, ResourceLocked
from apps.common.locks import LockAcquisitionError
from apps.jobs.models import JobType
from apps.jobs.services import create_job
from apps.organizations.services import check_and_reserve
from apps.virtual_machines.locks import lifecycle_lock
from apps.virtual_machines.mac import generate_mac_address
from apps.virtual_machines.models import ProvisioningState, VirtualMachine, VMDisk, VMNic, VMStatus

# Lifecycle operations that are only valid from certain current statuses.
# This is intentionally conservative -- the agent is still the ultimate
# authority (rule: never assume DB status is authoritative), but rejecting
# obviously-invalid transitions early gives fast, clear errors.
_ALLOWED_FROM = {
    JobType.VM_START: {VMStatus.STOPPED},
    JobType.VM_STOP: {VMStatus.RUNNING, VMStatus.PAUSED},
    JobType.VM_SHUTDOWN: {VMStatus.RUNNING},
    JobType.VM_REBOOT: {VMStatus.RUNNING},
    JobType.VM_RESET: {VMStatus.RUNNING, VMStatus.PAUSED},
    JobType.VM_PAUSE: {VMStatus.RUNNING},
    JobType.VM_RESUME: {VMStatus.PAUSED},
    JobType.VM_DELETE: {VMStatus.STOPPED, VMStatus.ERROR, VMStatus.CREATING},
    JobType.VM_CLONE: {VMStatus.STOPPED},
    JobType.VM_MIGRATE: {VMStatus.RUNNING, VMStatus.STOPPED},
}


@transaction.atomic
def create_vm(
    *,
    organization,
    project,
    name: str,
    created_by,
    node=None,
    template=None,
    cpu_count: int = 1,
    memory_mb: int = 2048,
    disks: list[dict] | None = None,
    nics: list[dict] | None = None,
    os_type: str = "linux",
    firmware: str = "BIOS",
    cloud_init_enabled: bool = False,
    cloud_init_config: dict | None = None,
    autostart: bool = False,
    idempotency_key: str = "",
) -> tuple[VirtualMachine, "Job"]:
    disks = disks or [{"name": "root", "size_bytes": 20 * 1024**3, "storage": None, "bootable": True}]
    nics = nics or []

    if idempotency_key:
        existing = VirtualMachine.objects.filter(created_by=created_by, idempotency_key=idempotency_key).first()
        if existing is not None:
            job = existing.jobs.order_by("-created_at").first()
            return existing, job

    total_disk_gb = sum(d["size_bytes"] for d in disks) // (1024**3)

    check_and_reserve(
        organization,
        project,
        additional_vms=1,
        additional_vcpu=cpu_count,
        additional_memory_mb=memory_mb,
        additional_storage_gb=total_disk_gb,
    )

    if node is None:
        from apps.virtual_machines.scheduler import SchedulingRequest, get_scheduler

        node = get_scheduler().select_node(
            SchedulingRequest(organization_id=organization.pk, cpu_count=cpu_count, memory_mb=memory_mb, disk_gb=total_disk_gb)
        )

    vm = VirtualMachine.objects.create(
        organization=organization,
        project=project,
        node=node,
        template=template,
        created_by=created_by,
        name=name,
        os_type=os_type,
        firmware=firmware,
        cpu_count=cpu_count,
        cpu_sockets=1,
        cpu_cores=cpu_count,
        cpu_threads=1,
        memory_mb=memory_mb,
        cloud_init_enabled=cloud_init_enabled,
        cloud_init_config=cloud_init_config or {},
        autostart=autostart,
        idempotency_key=idempotency_key,
        status=VMStatus.CREATING,
        provisioning_state=ProvisioningState.REQUESTED,
    )

    for index, disk_spec in enumerate(disks):
        VMDisk.objects.create(
            vm=vm,
            storage=disk_spec["storage"],
            name=disk_spec.get("name", f"disk-{index}"),
            bus=disk_spec.get("bus", "VIRTIO"),
            size_bytes=disk_spec["size_bytes"],
            format=disk_spec.get("format", "qcow2"),
            bootable=disk_spec.get("bootable", index == 0),
            boot_index=index,
        )

    for index, nic_spec in enumerate(nics):
        VMNic.objects.create(
            vm=vm,
            network=nic_spec["network"],
            mac_address=nic_spec.get("mac_address") or generate_mac_address(),
            model=nic_spec.get("model", "VIRTIO"),
            vlan=nic_spec.get("vlan"),
            bootable=nic_spec.get("bootable", index == 0),
            boot_index=index,
        )

    job = create_job(
        type=JobType.VM_CREATE,
        resource_type="VirtualMachine",
        resource_id=str(vm.uuid),
        organization=organization,
        node=node,
        created_by=created_by,
        idempotency_key=idempotency_key,
    )

    transaction.on_commit(lambda: _enqueue_provision(job.pk, vm.pk))
    return vm, job


def _enqueue_provision(job_id: int, vm_id: int) -> None:
    from apps.virtual_machines.tasks import provision_vm

    provision_vm.delay(job_id, vm_id)


def _start_lifecycle_job(vm: VirtualMachine, job_type: str, task_callable, *, requested_by) -> "Job":
    allowed = _ALLOWED_FROM.get(job_type)
    if allowed is not None and vm.status not in allowed:
        raise InvalidStateTransition(f"Cannot {job_type} a VM in status {vm.status}")

    # Fast, optimistic pre-check for immediate user feedback; the Celery
    # task re-acquires the same lock authoritatively for its duration.
    lock = lifecycle_lock(vm)
    if not lock.acquire(blocking=False):
        raise ResourceLocked(f"VM {vm.name} has another lifecycle operation in progress.")
    lock.release()

    job = create_job(
        type=job_type,
        resource_type="VirtualMachine",
        resource_id=str(vm.uuid),
        organization=vm.organization,
        node=vm.node,
        created_by=requested_by,
    )
    transaction.on_commit(lambda: task_callable.delay(job.pk, vm.pk))
    return job


def start_vm(vm, requested_by):
    from apps.virtual_machines.tasks import start_vm_task

    return _start_lifecycle_job(vm, JobType.VM_START, start_vm_task, requested_by=requested_by)


def stop_vm(vm, requested_by, force: bool = False):
    from apps.virtual_machines.tasks import stop_vm_task

    job_type = JobType.VM_STOP if force else JobType.VM_SHUTDOWN
    return _start_lifecycle_job(vm, job_type, stop_vm_task, requested_by=requested_by)


def reboot_vm(vm, requested_by, force: bool = False):
    from apps.virtual_machines.tasks import reboot_vm_task

    job_type = JobType.VM_RESET if force else JobType.VM_REBOOT
    return _start_lifecycle_job(vm, job_type, reboot_vm_task, requested_by=requested_by)


def pause_vm(vm, requested_by):
    from apps.virtual_machines.tasks import pause_vm_task

    return _start_lifecycle_job(vm, JobType.VM_PAUSE, pause_vm_task, requested_by=requested_by)


def resume_vm(vm, requested_by):
    from apps.virtual_machines.tasks import resume_vm_task

    return _start_lifecycle_job(vm, JobType.VM_RESUME, resume_vm_task, requested_by=requested_by)


def delete_vm(vm, requested_by):
    from apps.virtual_machines.tasks import delete_vm_task

    return _start_lifecycle_job(vm, JobType.VM_DELETE, delete_vm_task, requested_by=requested_by)


def clone_vm(vm, requested_by, *, new_name: str, linked: bool = False):
    from apps.virtual_machines.tasks import clone_vm_task

    if vm.status not in _ALLOWED_FROM[JobType.VM_CLONE]:
        raise InvalidStateTransition("VM must be stopped before cloning.")

    total_disk_gb = sum(d.size_bytes for d in vm.disks.all()) // (1024**3)
    check_and_reserve(
        vm.organization, vm.project,
        additional_vms=1, additional_vcpu=vm.cpu_count, additional_memory_mb=vm.memory_mb, additional_storage_gb=total_disk_gb,
    )

    job = create_job(
        type=JobType.VM_CLONE, resource_type="VirtualMachine", resource_id=str(vm.uuid),
        organization=vm.organization, node=vm.node, created_by=requested_by,
    )
    transaction.on_commit(lambda: clone_vm_task.delay(job.pk, vm.pk, new_name, linked))
    return job


def migrate_vm(vm, requested_by, *, target_node):
    """
    Verifies migration compatibility (section 44) before ever touching the
    agent. Live migration execution itself is Phase 9 (section 70) and is
    deliberately not performed yet -- claiming success here would violate
    rule 3 ("never claim an operation succeeded until the agent confirms
    it") for a code path this project has not built out.
    """
    from apps.common.exceptions import NodePilotAPIException

    class MigrationNotImplemented(NodePilotAPIException):
        code_name = "MIGRATION_NOT_IMPLEMENTED"
        status_code = 501
        default_detail = "Live migration execution is not yet implemented."

    if vm.status not in _ALLOWED_FROM[JobType.VM_MIGRATE]:
        raise InvalidStateTransition(f"Cannot migrate a VM in status {vm.status}")
    if target_node.organization_id != vm.organization_id:
        raise InvalidStateTransition("Target node must belong to the same organization.")
    if not target_node.is_schedulable():
        raise InvalidStateTransition("Target node is not online/schedulable.")

    incompatible_disks = [d for d in vm.disks.all() if not d.storage.shared]
    if incompatible_disks:
        raise NodePilotAPIException(
            "Migration requires all disks to live on shared storage visible to the target node; "
            "this VM has local (non-shared) storage.",
            code_name="MIGRATION_STORAGE_INCOMPATIBLE",
            details={"disks": [d.name for d in incompatible_disks]},
        )

    raise MigrationNotImplemented(
        "Compatibility checks passed, but live migration execution is not yet implemented in this "
        "release (see the roadmap in section 70/Phase 9). No changes were made."
    )
