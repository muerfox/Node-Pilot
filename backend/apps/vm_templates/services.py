"""Creating a VM from a Template is itself just a call into the same
transactional VM creation service every other VM goes through (section
16: "Creating a VM from a template should be a transactional background
job" -- the job/state-machine guarantees live in
apps.virtual_machines.services.create_vm / tasks.provision_vm). The one
template-specific piece is seeding the boot disk from the template's
image (VMDisk.source_image) instead of leaving it blank -- see
apps.virtual_machines.tasks.provision_vm's CREATE_DISK step and the
agent's disk_ops.create_disk for how that's actually carried out."""
from __future__ import annotations

from apps.common.exceptions import NodePilotAPIException
from apps.images.models import ImageStatus


class TemplateImageNotReady(NodePilotAPIException):
    code_name = "TEMPLATE_IMAGE_NOT_READY"
    status_code = 409


def create_vm_from_template(
    template,
    *,
    project,
    name: str,
    storage,
    network,
    created_by,
    node=None,
    cpu_count: int | None = None,
    memory_mb: int | None = None,
    disk_gb: int | None = None,
    autostart: bool = True,
    idempotency_key: str = "",
):
    from apps.virtual_machines.services import create_vm

    if template.image.status != ImageStatus.READY:
        raise TemplateImageNotReady(f"Template {template.name!r}'s image ({template.image.name}) is not ready yet (status: {template.image.status}).")

    return create_vm(
        organization=template.organization,
        project=project,
        name=name,
        created_by=created_by,
        node=node,
        template=template,
        cpu_count=cpu_count or template.default_cpu_count,
        memory_mb=memory_mb or template.default_memory_mb,
        disks=[
            {
                "storage": storage, "source_image": template.image, "name": "root",
                "size_bytes": (disk_gb or template.default_disk_gb) * 1024**3, "bootable": True,
            }
        ],
        nics=[{"network": network, "model": template.network_defaults.get("model", "VIRTIO")}],
        os_type=template.default_os_type,
        firmware=template.default_firmware,
        cloud_init_enabled=bool(template.cloud_init_defaults),
        cloud_init_config=template.cloud_init_defaults,
        autostart=autostart,
        idempotency_key=idempotency_key,
    )
