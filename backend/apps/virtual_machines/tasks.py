from __future__ import annotations

import logging

from celery import shared_task

from apps.common.locks import LockAcquisitionError
from apps.jobs.models import Job, JobStatus
from apps.jobs.services import job_run, transition
from apps.jobs.tasks import JobBoundTask
from apps.nodes import agent_client
from apps.nodes.protocol import OperationType
from apps.virtual_machines.locks import lifecycle_lock, storage_lock
from apps.virtual_machines.mac import generate_mac_address
from apps.virtual_machines.models import ProvisioningState, VirtualMachine, VMDisk, VMNic, VMStatus

logger = logging.getLogger("nodepilot.vm_tasks")


def _build_domain_payload(vm: VirtualMachine) -> dict:
    return {
        "domain_uuid": str(vm.domain_uuid),
        "name": vm.name,
        "os_type": vm.os_type,
        "firmware": vm.firmware,
        "machine_type": vm.machine_type,
        "cpu": {"count": vm.cpu_count, "sockets": vm.cpu_sockets, "cores": vm.cpu_cores, "threads": vm.cpu_threads, "model": vm.cpu_model},
        "memory_mb": vm.memory_mb,
        "ballooning_enabled": vm.ballooning_enabled,
        "boot_order": vm.boot_order or ["disk"],
        "disks": [
            {
                "uuid": str(d.uuid), "volume_id": d.volume_id, "bus": d.bus, "device": d.device,
                "bootable": d.bootable, "readonly": d.readonly, "discard": d.discard, "iothread": d.iothread,
                "boot_index": d.boot_index, "format": d.format, "storage_type": d.storage.type,
            }
            for d in vm.disks.select_related("storage").all()
        ],
        "nics": [
            {
                "uuid": str(n.uuid), "mac_address": n.mac_address, "model": n.model,
                "bridge": n.network.bridge, "vlan": n.vlan or n.network.vlan_id, "boot_index": n.boot_index,
            }
            for n in vm.nics.all()
        ],
    }


def _emit_vm_event(vm: VirtualMachine, event_type: str, **metadata) -> None:
    try:
        from apps.events.services import emit_event

        emit_event(
            type=event_type, severity="INFO", resource_type="VirtualMachine",
            resource_id=str(vm.uuid), organization=vm.organization, metadata=metadata,
        )
    except Exception:  # pragma: no cover
        logger.exception("Failed to emit %s for VM %s", event_type, vm.uuid)

    try:
        from apps.webhooks.services import dispatch_event

        dispatch_event(vm.organization, event_type.lower().replace("vm_", "vm."), {"vm_uuid": str(vm.uuid), "name": vm.name, **metadata})
    except Exception:  # pragma: no cover
        logger.exception("Failed to dispatch webhook for %s on VM %s", event_type, vm.uuid)

    try:
        from apps.virtual_machines.consumers import broadcast_vm_status

        broadcast_vm_status(vm)
    except Exception:  # pragma: no cover
        logger.exception("Failed to broadcast VM status for %s", vm.uuid)


def _cleanup_partial_vm(vm: VirtualMachine) -> None:
    """Best-effort teardown of whatever got created before the failure
    (rule: never leave orphaned disks/NICs silently). Failures here are
    logged and turned into an event -- they are not swallowed."""
    problems = []
    if vm.provisioning_state in {ProvisioningState.DOMAIN_CREATED, ProvisioningState.CLOUD_INIT_ATTACHED, ProvisioningState.STARTED}:
        try:
            agent_client.send_operation(vm.node, OperationType.DELETE_VM, resource_id=str(vm.uuid), payload={"delete_disks": False})
        except Exception as exc:  # pragma: no cover
            problems.append(f"domain cleanup: {exc}")
    for disk in vm.disks.select_related("storage").filter(volume_id__gt=""):
        try:
            agent_client.send_operation(
                vm.node, OperationType.DELETE_DISK, resource_id=str(vm.uuid),
                payload={"volume_id": disk.volume_id, "storage_id": disk.storage_id, "storage_type": disk.storage.type, "storage_path": disk.storage.path},
            )
        except Exception as exc:  # pragma: no cover
            problems.append(f"disk {disk.name}: {exc}")

    if problems:
        _emit_vm_event(vm, "VM_CLEANUP_INCOMPLETE", problems=problems)


@shared_task(bind=True, base=JobBoundTask)
def provision_vm(self, job_id: int, vm_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    vm = VirtualMachine.objects.select_related("node", "organization").get(pk=vm_id)

    try:
        with lifecycle_lock(vm):
            with job_run(job, "Allocating resources"):
                vm.provisioning_state = ProvisioningState.ALLOCATING
                vm.save(update_fields=["provisioning_state"])

            with job_run(job, "Creating disks"):
                for disk in vm.disks.select_related("storage").all():
                    data = agent_client.send_operation(
                        vm.node, OperationType.CREATE_DISK, resource_id=str(vm.uuid),
                        payload={
                            "disk_uuid": str(disk.uuid), "storage_id": disk.storage_id, "storage_path": disk.storage.path,
                            "storage_type": disk.storage.type, "size_bytes": disk.size_bytes, "format": disk.format,
                            "name": disk.name,
                        },
                    )
                    disk.volume_id = data.get("volume_id", "")
                    disk.device = data.get("device", disk.device)
                    # The agent's response is authoritative for format --
                    # LVM/LVM-thin/ZFS backends always produce a raw block
                    # device regardless of what was requested, and the
                    # domain XML built two steps from now needs to match
                    # what was actually created, not what we asked for.
                    disk.format = data.get("format", disk.format)
                    disk.save(update_fields=["volume_id", "device", "format"])
                vm.provisioning_state = ProvisioningState.DISK_CREATED
                vm.save(update_fields=["provisioning_state"])

            with job_run(job, "Configuring network"):
                vm.provisioning_state = ProvisioningState.NETWORK_CREATED
                vm.save(update_fields=["provisioning_state"])

            with job_run(job, "Creating domain"):
                agent_client.send_operation(vm.node, OperationType.CREATE_VM, resource_id=str(vm.uuid), payload=_build_domain_payload(vm))
                vm.provisioning_state = ProvisioningState.DOMAIN_CREATED
                vm.save(update_fields=["provisioning_state"])

            if vm.cloud_init_enabled:
                with job_run(job, "Attaching cloud-init"):
                    agent_client.send_operation(
                        vm.node, OperationType.GENERATE_CLOUD_INIT, resource_id=str(vm.uuid),
                        payload={"cloud_init": vm.cloud_init_config},
                    )
            vm.provisioning_state = ProvisioningState.CLOUD_INIT_ATTACHED
            vm.save(update_fields=["provisioning_state"])

            if vm.autostart:
                with job_run(job, "Starting VM"):
                    agent_client.send_operation(vm.node, OperationType.START_VM, resource_id=str(vm.uuid))
                    vm.status = VMStatus.RUNNING
                    vm.provisioning_state = ProvisioningState.STARTED
                    vm.save(update_fields=["status", "provisioning_state"])
            else:
                vm.status = VMStatus.STOPPED

            vm.provisioning_state = ProvisioningState.READY
            vm.save(update_fields=["status", "provisioning_state"])

        transition(job, JobStatus.SUCCESS, message="VM created successfully")
        _emit_vm_event(vm, "VM_CREATED")

    except LockAcquisitionError as exc:
        if not job.is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise
    except Exception as exc:
        _cleanup_partial_vm(vm)
        vm.status = VMStatus.ERROR
        vm.provisioning_state = ProvisioningState.ERROR
        vm.last_error = str(exc)
        vm.save(update_fields=["status", "provisioning_state", "last_error"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


def _simple_lifecycle_task(job_id: int, vm_id: int, operation: OperationType, running_status: str, step_message: str, event_type: str, payload: dict | None = None) -> None:
    job = Job.objects.get(pk=job_id)
    vm = VirtualMachine.objects.select_related("node", "organization").get(pk=vm_id)
    try:
        with lifecycle_lock(vm):
            with job_run(job, step_message):
                agent_client.send_operation(vm.node, operation, resource_id=str(vm.uuid), payload=payload or {})
                vm.status = running_status
                vm.save(update_fields=["status"])
        transition(job, JobStatus.SUCCESS, message=step_message)
        _emit_vm_event(vm, event_type)
    except Exception as exc:
        vm.last_error = str(exc)
        vm.save(update_fields=["last_error"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def start_vm_task(self, job_id: int, vm_id: int) -> None:
    _simple_lifecycle_task(job_id, vm_id, OperationType.START_VM, VMStatus.RUNNING, "Starting VM", "VM_STARTED")


@shared_task(bind=True, base=JobBoundTask)
def stop_vm_task(self, job_id: int, vm_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    force = job.type == "VM_STOP"
    operation = OperationType.STOP_VM if force else OperationType.SHUTDOWN_VM
    _simple_lifecycle_task(job_id, vm_id, operation, VMStatus.STOPPED, "Stopping VM" if force else "Shutting down VM", "VM_STOPPED")


@shared_task(bind=True, base=JobBoundTask)
def reboot_vm_task(self, job_id: int, vm_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    force = job.type == "VM_RESET"
    operation = OperationType.RESET_VM if force else OperationType.REBOOT_VM
    _simple_lifecycle_task(job_id, vm_id, operation, VMStatus.RUNNING, "Resetting VM" if force else "Rebooting VM", "VM_REBOOTED")


@shared_task(bind=True, base=JobBoundTask)
def pause_vm_task(self, job_id: int, vm_id: int) -> None:
    _simple_lifecycle_task(job_id, vm_id, OperationType.PAUSE_VM, VMStatus.PAUSED, "Pausing VM", "VM_PAUSED")


@shared_task(bind=True, base=JobBoundTask)
def resume_vm_task(self, job_id: int, vm_id: int) -> None:
    _simple_lifecycle_task(job_id, vm_id, OperationType.RESUME_VM, VMStatus.RUNNING, "Resuming VM", "VM_RESUMED")


@shared_task(bind=True, base=JobBoundTask)
def delete_vm_task(self, job_id: int, vm_id: int) -> None:
    job = Job.objects.get(pk=job_id)
    vm = VirtualMachine.objects.select_related("node", "organization").get(pk=vm_id)
    try:
        with lifecycle_lock(vm), storage_lock(vm):
            with job_run(job, "Deleting VM"):
                vm.status = VMStatus.DELETING
                vm.save(update_fields=["status"])
                agent_client.send_operation(vm.node, OperationType.DELETE_VM, resource_id=str(vm.uuid), payload={"delete_disks": True})
                for disk in vm.disks.select_related("storage").filter(volume_id__gt=""):
                    agent_client.send_operation(
                        vm.node, OperationType.DELETE_DISK, resource_id=str(vm.uuid),
                        payload={"volume_id": disk.volume_id, "storage_id": disk.storage_id, "storage_type": disk.storage.type, "storage_path": disk.storage.path},
                    )
        vm_uuid, vm_name, org = vm.uuid, vm.name, vm.organization
        vm.delete()
        transition(job, JobStatus.SUCCESS, message="VM deleted")
        try:
            from apps.events.services import emit_event

            emit_event(type="VM_DELETED", severity="INFO", resource_type="VirtualMachine", resource_id=str(vm_uuid), organization=org, metadata={"name": vm_name})
        except Exception:  # pragma: no cover
            logger.exception("Failed to emit VM_DELETED for %s", vm_uuid)
    except Exception as exc:
        vm.status = VMStatus.ERROR
        vm.last_error = str(exc)
        vm.save(update_fields=["status", "last_error"])
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def clone_vm_task(self, job_id: int, vm_id: int, new_name: str, linked: bool) -> None:
    """
    Full or linked clone (section 25). Always mints a brand new VM UUID,
    disk UUIDs, MAC addresses, and hostname -- never duplicates the
    source's identity.
    """
    job = Job.objects.get(pk=job_id)
    source = VirtualMachine.objects.select_related("node", "organization", "project").get(pk=vm_id)

    try:
        with lifecycle_lock(source), storage_lock(source):
            with job_run(job, "Preparing clone"):
                clone = VirtualMachine.objects.create(
                    organization=source.organization, project=source.project, node=source.node,
                    created_by=job.created_by, name=new_name, os_type=source.os_type, firmware=source.firmware,
                    machine_type=source.machine_type, cpu_count=source.cpu_count, cpu_sockets=source.cpu_sockets,
                    cpu_cores=source.cpu_cores, cpu_threads=source.cpu_threads, cpu_model=source.cpu_model,
                    memory_mb=source.memory_mb, cloud_init_enabled=source.cloud_init_enabled,
                    autostart=False, status=VMStatus.CREATING, provisioning_state=ProvisioningState.REQUESTED,
                )
                job.resource_id = str(clone.uuid)
                job.save(update_fields=["resource_id"])

            with job_run(job, "Cloning disks"):
                for disk in source.disks.select_related("storage").all():
                    data = agent_client.send_operation(
                        source.node, OperationType.CLONE_DISK, resource_id=str(source.uuid),
                        payload={
                            "source_volume_id": disk.volume_id, "storage_id": disk.storage_id,
                            "storage_type": disk.storage.type, "storage_path": disk.storage.path,
                            "new_name": f"{clone.uuid}-{disk.name}", "linked": linked,
                        },
                    )
                    VMDisk.objects.create(
                        vm=clone, storage=disk.storage, name=disk.name, volume_id=data.get("volume_id", ""),
                        device=disk.device, bus=disk.bus, size_bytes=disk.size_bytes, format=disk.format,
                        bootable=disk.bootable, readonly=disk.readonly, discard=disk.discard,
                        iothread=disk.iothread, boot_index=disk.boot_index,
                    )
                clone.provisioning_state = ProvisioningState.DISK_CREATED
                clone.save(update_fields=["provisioning_state"])

            with job_run(job, "Assigning new network identity"):
                for nic in source.nics.select_related("network").all():
                    VMNic.objects.create(
                        vm=clone, network=nic.network, mac_address=generate_mac_address(),
                        model=nic.model, vlan=nic.vlan, bootable=nic.bootable, boot_index=nic.boot_index,
                    )
                clone.provisioning_state = ProvisioningState.NETWORK_CREATED
                clone.save(update_fields=["provisioning_state"])

            with job_run(job, "Creating cloned domain"):
                agent_client.send_operation(clone.node, OperationType.CREATE_VM, resource_id=str(clone.uuid), payload=_build_domain_payload(clone))
                clone.provisioning_state = ProvisioningState.READY
                clone.status = VMStatus.STOPPED
                clone.save(update_fields=["provisioning_state", "status"])

        transition(job, JobStatus.SUCCESS, message=f"Cloned to {new_name}")
        _emit_vm_event(clone, "VM_CLONED", source_uuid=str(source.uuid))
    except Exception as exc:
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


def _disk_or_nic_task(job_id: int, obj, *, step: str, run_op) -> None:
    """Shared body for the five standalone disk/NIC hot-plug operations
    below: hold the storage lock, run one agent op, transition the job,
    and roll the job to FAILED (never silently) on any error."""
    job = Job.objects.get(pk=job_id)
    vm = obj.vm
    try:
        with storage_lock(vm):
            with job_run(job, step):
                run_op()
        transition(job, JobStatus.SUCCESS, message=step)
    except Exception as exc:
        if not Job.objects.get(pk=job.pk).is_terminal:
            transition(job, JobStatus.FAILED, error=str(exc))
        raise


@shared_task(bind=True, base=JobBoundTask)
def attach_disk_task(self, job_id: int, disk_id: int) -> None:
    disk = VMDisk.objects.select_related("vm", "vm__node", "storage").get(pk=disk_id)

    def run():
        data = agent_client.send_operation(
            disk.vm.node, OperationType.CREATE_DISK, resource_id=str(disk.vm.uuid),
            payload={"disk_uuid": str(disk.uuid), "storage_id": disk.storage_id, "storage_path": disk.storage.path, "storage_type": disk.storage.type, "size_bytes": disk.size_bytes, "format": disk.format},
        )
        disk.volume_id = data.get("volume_id", "")
        disk.device = data.get("device", disk.device)
        disk.format = data.get("format", disk.format)  # authoritative -- see provision_vm's CREATE_DISK step
        disk.save(update_fields=["volume_id", "device", "format"])
        agent_client.send_operation(
            disk.vm.node, OperationType.ATTACH_DISK, resource_id=str(disk.vm.uuid),
            payload={
                "domain_uuid": str(disk.vm.domain_uuid), "volume_id": disk.volume_id, "device": disk.device or "vdb",
                "bus": disk.bus, "storage_type": disk.storage.type, "format": disk.format,
            },
        )

    _disk_or_nic_task(job_id, disk, step=f"Attaching disk {disk.name}", run_op=run)


@shared_task(bind=True, base=JobBoundTask)
def detach_disk_task(self, job_id: int, disk_id: int) -> None:
    disk = VMDisk.objects.select_related("vm", "vm__node", "storage").get(pk=disk_id)
    disk_uuid, vm = disk.uuid, disk.vm

    def run():
        agent_client.send_operation(
            vm.node, OperationType.DETACH_DISK, resource_id=str(vm.uuid),
            payload={
                "domain_uuid": str(vm.domain_uuid), "volume_id": disk.volume_id, "device": disk.device, "bus": disk.bus,
                "storage_type": disk.storage.type, "format": disk.format,
            },
        )
        if disk.volume_id:
            agent_client.send_operation(
                vm.node, OperationType.DELETE_DISK, resource_id=str(vm.uuid),
                payload={"volume_id": disk.volume_id, "storage_id": disk.storage_id, "storage_type": disk.storage.type, "storage_path": disk.storage.path},
            )
        disk.delete()

    _disk_or_nic_task(job_id, disk, step=f"Detaching disk {disk_uuid}", run_op=run)


@shared_task(bind=True, base=JobBoundTask)
def resize_disk_task(self, job_id: int, disk_id: int, new_size_bytes: int) -> None:
    disk = VMDisk.objects.select_related("vm", "vm__node", "storage").get(pk=disk_id)

    def run():
        agent_client.send_operation(
            disk.vm.node, OperationType.RESIZE_DISK, resource_id=str(disk.vm.uuid),
            payload={"volume_id": disk.volume_id, "storage_id": disk.storage_id, "storage_type": disk.storage.type, "storage_path": disk.storage.path, "new_size_bytes": new_size_bytes},
        )
        disk.size_bytes = new_size_bytes
        disk.save(update_fields=["size_bytes"])

    _disk_or_nic_task(job_id, disk, step=f"Resizing disk {disk.name}", run_op=run)


@shared_task(bind=True, base=JobBoundTask)
def attach_nic_task(self, job_id: int, nic_id: int) -> None:
    nic = VMNic.objects.select_related("vm", "vm__node", "network").get(pk=nic_id)

    def run():
        agent_client.send_operation(
            nic.vm.node, OperationType.ATTACH_NIC, resource_id=str(nic.vm.uuid),
            payload={
                "domain_uuid": str(nic.vm.domain_uuid), "bridge": nic.network.bridge, "vlan": nic.vlan or nic.network.vlan_id,
                "mac_address": nic.mac_address, "model": nic.model,
            },
        )

    _disk_or_nic_task(job_id, nic, step=f"Attaching NIC {nic.mac_address}", run_op=run)


@shared_task(bind=True, base=JobBoundTask)
def detach_nic_task(self, job_id: int, nic_id: int) -> None:
    nic = VMNic.objects.select_related("vm", "vm__node", "network").get(pk=nic_id)
    mac, vm = nic.mac_address, nic.vm

    def run():
        agent_client.send_operation(
            vm.node, OperationType.DETACH_NIC, resource_id=str(vm.uuid),
            payload={
                "domain_uuid": str(vm.domain_uuid), "bridge": nic.network.bridge, "vlan": nic.vlan or nic.network.vlan_id,
                "mac_address": nic.mac_address, "model": nic.model,
            },
        )
        nic.delete()

    _disk_or_nic_task(job_id, nic, step=f"Detaching NIC {mac}", run_op=run)
