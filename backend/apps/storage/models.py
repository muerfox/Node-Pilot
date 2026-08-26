from django.db import models

from apps.common.models import NodePilotModel


class StorageType(models.TextChoices):
    DIRECTORY = "DIRECTORY", "Directory"
    LVM = "LVM", "LVM"
    LVM_THIN = "LVM_THIN", "LVM-thin"
    ZFS = "ZFS", "ZFS"
    NFS = "NFS", "NFS"
    CEPH_RBD = "CEPH_RBD", "Ceph RBD"


class StorageCapability(models.TextChoices):
    VM_DISK = "VM_DISK", "VM disk"
    ISO = "ISO", "ISO"
    BACKUP = "BACKUP", "Backup"
    SNAPSHOT = "SNAPSHOT", "Snapshot"
    TEMPLATE = "TEMPLATE", "Template"


# Not every backend can do everything -- section 14/24: "advertise
# capabilities rather than relying on hardcoded assumptions" and don't
# pretend every storage backend supports identical snapshot semantics.
# This is the *default* capability set a pool of a given type is created
# with; operators may narrow it per-pool (e.g. an NFS pool with no CoW
# support could have SNAPSHOT capability removed).
DEFAULT_CAPABILITIES_BY_TYPE: dict[str, list[str]] = {
    StorageType.DIRECTORY: [StorageCapability.VM_DISK, StorageCapability.ISO, StorageCapability.BACKUP, StorageCapability.TEMPLATE],
    StorageType.LVM: [StorageCapability.VM_DISK],
    StorageType.LVM_THIN: [StorageCapability.VM_DISK, StorageCapability.SNAPSHOT],
    StorageType.ZFS: [StorageCapability.VM_DISK, StorageCapability.SNAPSHOT, StorageCapability.TEMPLATE],
    StorageType.NFS: [StorageCapability.VM_DISK, StorageCapability.ISO, StorageCapability.BACKUP, StorageCapability.TEMPLATE],
    StorageType.CEPH_RBD: [StorageCapability.VM_DISK, StorageCapability.SNAPSHOT],
}


class StoragePoolStatus(models.TextChoices):
    ONLINE = "ONLINE", "Online"
    OFFLINE = "OFFLINE", "Offline"
    WARNING = "WARNING", "Warning"
    ERROR = "ERROR", "Error"


class StoragePool(NodePilotModel):
    """A storage pool exposed by a single node (section 14)."""

    node = models.ForeignKey("nodes.Node", on_delete=models.CASCADE, related_name="storage_pools")
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=StorageType.choices)
    path = models.CharField(max_length=500, help_text="Mount point, volume group, dataset, or export path on the node.")

    capacity_bytes = models.BigIntegerField(default=0)
    used_bytes = models.BigIntegerField(default=0)
    available_bytes = models.BigIntegerField(default=0)

    status = models.CharField(max_length=10, choices=StoragePoolStatus.choices, default=StoragePoolStatus.ONLINE)
    shared = models.BooleanField(default=False, help_text="Visible/usable from more than one node -- required for migration.")
    enabled = models.BooleanField(default=True)
    capabilities = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "storage_pools"
        unique_together = [("node", "name")]
        ordering = ["node_id", "name"]

    def __str__(self) -> str:
        return f"{self.node.name}/{self.name}"

    def save(self, *args, **kwargs):
        if not self.capabilities:
            self.capabilities = DEFAULT_CAPABILITIES_BY_TYPE.get(self.type, [])
        super().save(*args, **kwargs)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    @property
    def free_gb(self) -> int:
        return self.available_bytes // (1024**3)
