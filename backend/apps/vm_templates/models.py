from django.db import models

from apps.common.models import NodePilotModel


class Template(NodePilotModel):
    """A reusable VM blueprint (section 16), e.g. "Ubuntu 24.04"."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="templates")
    image = models.ForeignKey("images.Image", on_delete=models.PROTECT, related_name="templates")

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    default_cpu_count = models.PositiveIntegerField(default=2)
    default_memory_mb = models.PositiveIntegerField(default=4096)
    default_disk_gb = models.PositiveIntegerField(default=20)
    default_firmware = models.CharField(max_length=10, default="BIOS")
    default_os_type = models.CharField(max_length=100, default="linux")

    network_defaults = models.JSONField(default=dict, blank=True, help_text='e.g. {"model": "VIRTIO", "count": 1}')
    cloud_init_defaults = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "vm_templates"
        unique_together = [("organization", "name")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
