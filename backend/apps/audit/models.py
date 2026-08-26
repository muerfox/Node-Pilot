from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class AuditResult(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILURE = "FAILURE", "Failure"


class AuditLog(NodePilotModel):
    """
    Every important administrative operation must be logged (section 30)
    and immutable once written -- rows can only be inserted, never updated
    or deleted, from application code (Django admin superusers retain raw
    DB access, which is outside "the normal UI").
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    actor_label = models.CharField(max_length=255, blank=True, default="", help_text="Denormalized actor identity, kept even if the user is later deleted.")
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=100, db_index=True)
    resource_id = models.CharField(max_length=100, blank=True, default="")
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    result = models.CharField(max_length=20, choices=AuditResult.choices, default=AuditResult.SUCCESS)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.resource_type}:{self.resource_id} by {self.actor_label} -> {self.result}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLog entries are immutable and cannot be deleted.")
