import uuid

from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class VMStatus(models.TextChoices):
    """Hypervisor-facing lifecycle status (section 10). The DB value is a
    cache of the last known state -- callers that need certainty must
    query the agent (see apps.virtual_machines.services.refresh_status)."""

    CREATING = "CREATING", "Creating"
    STOPPED = "STOPPED", "Stopped"
    RUNNING = "RUNNING", "Running"
    PAUSED = "PAUSED", "Paused"
    SUSPENDED = "SUSPENDED", "Suspended"
    MIGRATING = "MIGRATING", "Migrating"
    ERROR = "ERROR", "Error"
    DELETING = "DELETING", "Deleting"
    UNKNOWN = "UNKNOWN", "Unknown"


class ProvisioningState(models.TextChoices):
    """Internal creation state machine (section 50)."""

    REQUESTED = "REQUESTED", "Requested"
    ALLOCATING = "ALLOCATING", "Allocating"
    DISK_CREATED = "DISK_CREATED", "Disk created"
    NETWORK_CREATED = "NETWORK_CREATED", "Network created"
    DOMAIN_CREATED = "DOMAIN_CREATED", "Domain created"
    CLOUD_INIT_ATTACHED = "CLOUD_INIT_ATTACHED", "Cloud-init attached"
    STARTED = "STARTED", "Started"
    READY = "READY", "Ready"
    ERROR = "ERROR", "Error"


PROVISIONING_ORDER = [
    ProvisioningState.REQUESTED,
    ProvisioningState.ALLOCATING,
    ProvisioningState.DISK_CREATED,
    ProvisioningState.NETWORK_CREATED,
    ProvisioningState.DOMAIN_CREATED,
    ProvisioningState.CLOUD_INIT_ATTACHED,
    ProvisioningState.STARTED,
    ProvisioningState.READY,
]


class FirmwareType(models.TextChoices):
    BIOS = "BIOS", "BIOS"
    UEFI = "UEFI", "UEFI"


class DiskBus(models.TextChoices):
    VIRTIO = "VIRTIO", "VirtIO"
    VIRTIO_SCSI = "VIRTIO_SCSI", "VirtIO SCSI"
    SATA = "SATA", "SATA"
    IDE = "IDE", "IDE"


class NicModel(models.TextChoices):
    VIRTIO = "VIRTIO", "VirtIO"
    E1000 = "E1000", "E1000"


class VirtualMachine(NodePilotModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="virtual_machines")
    project = models.ForeignKey("organizations.Project", on_delete=models.CASCADE, related_name="virtual_machines")
    node = models.ForeignKey("nodes.Node", on_delete=models.PROTECT, related_name="virtual_machines", null=True, blank=True)
    template = models.ForeignKey("vm_templates.Template", on_delete=models.SET_NULL, null=True, blank=True, related_name="vms")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_vms")

    name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=VMStatus.choices, default=VMStatus.CREATING, db_index=True)
    provisioning_state = models.CharField(max_length=30, choices=ProvisioningState.choices, default=ProvisioningState.REQUESTED)

    os_type = models.CharField(max_length=100, blank=True, default="linux")
    firmware = models.CharField(max_length=10, choices=FirmwareType.choices, default=FirmwareType.BIOS)
    machine_type = models.CharField(max_length=50, default="q35")

    cpu_count = models.PositiveIntegerField(default=1)
    cpu_sockets = models.PositiveIntegerField(default=1)
    cpu_cores = models.PositiveIntegerField(default=1)
    cpu_threads = models.PositiveIntegerField(default=1)
    cpu_model = models.CharField(max_length=100, default="host-passthrough")

    memory_mb = models.PositiveIntegerField(default=2048)
    min_memory_mb = models.PositiveIntegerField(null=True, blank=True)
    max_memory_mb = models.PositiveIntegerField(null=True, blank=True)
    ballooning_enabled = models.BooleanField(default=True)

    boot_order = models.JSONField(default=list, blank=True, help_text='e.g. ["disk", "cdrom", "network"]')
    autostart = models.BooleanField(default=False)
    cloud_init_enabled = models.BooleanField(default=False)
    cloud_init_config = models.JSONField(default=dict, blank=True)

    domain_uuid = models.UUIDField(default=uuid.uuid4, unique=True, help_text="The libvirt domain UUID -- distinct from our own `uuid` public id.")

    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    last_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "virtual_machines"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"]), models.Index(fields=["node", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="unique_vm_name_per_project"),
            models.UniqueConstraint(
                fields=["created_by", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_vm_idempotency_key_per_user",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class VMDisk(NodePilotModel):
    vm = models.ForeignKey(VirtualMachine, on_delete=models.CASCADE, related_name="disks")
    storage = models.ForeignKey("storage.StoragePool", on_delete=models.PROTECT, related_name="disks")
    source_image = models.ForeignKey(
        "images.Image", on_delete=models.SET_NULL, null=True, blank=True, related_name="disks_created_from",
        help_text="Set when this disk was seeded from an image at creation time (e.g. deploying from a Template) -- provenance only; CREATE_DISK consumes it once and never re-reads it after.",
    )

    name = models.CharField(max_length=255)
    volume_id = models.CharField(max_length=255, blank=True, default="", help_text="Agent/storage-backend-assigned volume identifier or path.")
    bus = models.CharField(max_length=20, choices=DiskBus.choices, default=DiskBus.VIRTIO)
    device = models.CharField(max_length=20, blank=True, default="", help_text="e.g. vda, sdb")
    size_bytes = models.BigIntegerField()
    format = models.CharField(max_length=10, default="qcow2")
    bootable = models.BooleanField(default=False)
    readonly = models.BooleanField(default=False)
    discard = models.BooleanField(default=True)
    iothread = models.BooleanField(default=False)
    boot_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "vm_disks"
        ordering = ["boot_index", "created_at"]

    def __str__(self) -> str:
        return f"{self.vm.name}:{self.device or self.name}"


class VMNic(NodePilotModel):
    vm = models.ForeignKey(VirtualMachine, on_delete=models.CASCADE, related_name="nics")
    network = models.ForeignKey("networks.Network", on_delete=models.PROTECT, related_name="nics")
    ip_address = models.OneToOneField("networks.IPAddress", on_delete=models.SET_NULL, null=True, blank=True, related_name="nic")

    mac_address = models.CharField(max_length=17, unique=True)
    model = models.CharField(max_length=10, choices=NicModel.choices, default=NicModel.VIRTIO)
    vlan = models.PositiveIntegerField(null=True, blank=True)
    rate_limit_mbps = models.PositiveIntegerField(null=True, blank=True)
    bootable = models.BooleanField(default=False)
    boot_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "vm_nics"
        ordering = ["boot_index", "created_at"]

    def __str__(self) -> str:
        return f"{self.vm.name}:{self.mac_address}"
