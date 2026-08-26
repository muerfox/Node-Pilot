from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class EventSeverity(models.TextChoices):
    INFO = "INFO", "Info"
    WARNING = "WARNING", "Warning"
    CRITICAL = "CRITICAL", "Critical"


class Event(NodePilotModel):
    """
    Platform event stream (section 29): VM_CREATED, VM_STARTED,
    NODE_OFFLINE, STORAGE_WARNING, BACKUP_FAILED, etc. Distinct from
    AuditLog (section 30) -- events describe what happened to the system
    (including things no human triggered, like NODE_OFFLINE), while audit
    logs describe who did what.
    """

    type = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(max_length=10, choices=EventSeverity.choices, default=EventSeverity.INFO)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.type} [{self.severity}] {self.resource_type}:{self.resource_id}"
