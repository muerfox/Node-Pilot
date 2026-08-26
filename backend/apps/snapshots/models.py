from django.db import models

from apps.common.models import NodePilotModel


class SnapshotStatus(models.TextChoices):
    CREATING = "CREATING", "Creating"
    READY = "READY", "Ready"
    DELETING = "DELETING", "Deleting"
    ROLLING_BACK = "ROLLING_BACK", "Rolling back"
    ERROR = "ERROR", "Error"


class Snapshot(NodePilotModel):
    """VM snapshot (section 24). Storage-capability-aware: only created
    against disks whose StoragePool advertises SNAPSHOT support -- not
    every backend has identical (or any) snapshot semantics."""

    vm = models.ForeignKey("virtual_machines.VirtualMachine", on_delete=models.CASCADE, related_name="snapshots")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=15, choices=SnapshotStatus.choices, default=SnapshotStatus.CREATING)
    size_bytes = models.BigIntegerField(default=0)
    agent_snapshot_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "snapshots"
        unique_together = [("vm", "name")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.vm.name}@{self.name}"
