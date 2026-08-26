from django.db import models

from apps.common.models import NodePilotModel


class BackupTargetType(models.TextChoices):
    LOCAL = "LOCAL", "Local"
    NFS = "NFS", "NFS"
    S3 = "S3", "S3"
    MINIO = "MINIO", "MinIO"
    CEPH = "CEPH", "Ceph"


class BackupTarget(NodePilotModel):
    """A destination backups are written to (section 26)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="backup_targets")
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=BackupTargetType.choices)
    config = models.JSONField(default=dict, blank=True, help_text="Endpoint/bucket/path/credential-reference config for this target.")
    encryption_key_id = models.CharField(max_length=255, blank=True, default="", help_text="Reference to an externally-managed key; NodePilot never stores raw key material.")
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "backup_targets"
        unique_together = [("organization", "name")]

    def __str__(self) -> str:
        return self.name


class BackupType(models.TextChoices):
    FULL = "FULL", "Full"
    INCREMENTAL = "INCREMENTAL", "Incremental"
    SNAPSHOT = "SNAPSHOT", "Snapshot-based"


class BackupStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    VERIFYING = "VERIFYING", "Verifying"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    RESTORING = "RESTORING", "Restoring"
    DELETED = "DELETED", "Deleted"


class Backup(NodePilotModel):
    vm = models.ForeignKey("virtual_machines.VirtualMachine", on_delete=models.CASCADE, related_name="backups")
    target = models.ForeignKey(BackupTarget, on_delete=models.PROTECT, related_name="backups")
    type = models.CharField(max_length=15, choices=BackupType.choices, default=BackupType.FULL)
    status = models.CharField(max_length=10, choices=BackupStatus.choices, default=BackupStatus.PENDING)

    size_bytes = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="")
    encrypted = models.BooleanField(default=False)
    agent_backup_ref = models.CharField(max_length=500, blank=True, default="")

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    retention_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "backups"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.vm.name} @ {self.created_at:%Y-%m-%d %H:%M} [{self.status}]"


class BackupSchedule(NodePilotModel):
    """Recurring backup, driven by Celery Beat (section 27) via a linked
    django_celery_beat PeriodicTask."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="backup_schedules")
    vm = models.ForeignKey("virtual_machines.VirtualMachine", on_delete=models.CASCADE, related_name="backup_schedules")
    target = models.ForeignKey(BackupTarget, on_delete=models.CASCADE, related_name="schedules")
    backup_type = models.CharField(max_length=15, choices=BackupType.choices, default=BackupType.FULL)

    cron_expression = models.CharField(max_length=100, help_text="Standard 5-field cron expression, evaluated in `timezone`.")
    timezone = models.CharField(max_length=64, default="UTC")
    retention_days = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)

    periodic_task = models.OneToOneField("django_celery_beat.PeriodicTask", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        db_table = "backup_schedules"

    def __str__(self) -> str:
        return f"{self.vm.name} -> {self.target.name} ({self.cron_expression})"
