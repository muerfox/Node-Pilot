from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class JobType(models.TextChoices):
    VM_CREATE = "VM_CREATE", "Create VM"
    VM_START = "VM_START", "Start VM"
    VM_STOP = "VM_STOP", "Stop VM"
    VM_SHUTDOWN = "VM_SHUTDOWN", "Shutdown VM"
    VM_REBOOT = "VM_REBOOT", "Reboot VM"
    VM_RESET = "VM_RESET", "Reset VM"
    VM_PAUSE = "VM_PAUSE", "Pause VM"
    VM_RESUME = "VM_RESUME", "Resume VM"
    VM_DELETE = "VM_DELETE", "Delete VM"
    VM_CLONE = "VM_CLONE", "Clone VM"
    VM_MIGRATE = "VM_MIGRATE", "Migrate VM"
    DISK_CREATE = "DISK_CREATE", "Create disk"
    DISK_DELETE = "DISK_DELETE", "Delete disk"
    DISK_RESIZE = "DISK_RESIZE", "Resize disk"
    DISK_ATTACH = "DISK_ATTACH", "Attach disk"
    DISK_DETACH = "DISK_DETACH", "Detach disk"
    NIC_ATTACH = "NIC_ATTACH", "Attach NIC"
    NIC_DETACH = "NIC_DETACH", "Detach NIC"
    SNAPSHOT_CREATE = "SNAPSHOT_CREATE", "Create snapshot"
    SNAPSHOT_DELETE = "SNAPSHOT_DELETE", "Delete snapshot"
    SNAPSHOT_ROLLBACK = "SNAPSHOT_ROLLBACK", "Roll back snapshot"
    BACKUP_CREATE = "BACKUP_CREATE", "Create backup"
    BACKUP_RESTORE = "BACKUP_RESTORE", "Restore backup"
    IMAGE_IMPORT = "IMAGE_IMPORT", "Import image"
    WEBHOOK_DELIVERY = "WEBHOOK_DELIVERY", "Deliver webhook"


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    CANCELING = "CANCELING", "Canceling"
    CANCELED = "CANCELED", "Canceled"


TERMINAL_STATUSES = {JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELED}

VALID_TRANSITIONS: dict[str, set[str]] = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.CANCELING, JobStatus.CANCELED, JobStatus.FAILED},
    JobStatus.RUNNING: {JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELING},
    JobStatus.CANCELING: {JobStatus.CANCELED, JobStatus.FAILED, JobStatus.SUCCESS},
    JobStatus.SUCCESS: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELED: set(),
}


class Job(NodePilotModel):
    """
    Central unit of work for every long-running operation (section 19).
    HTTP handlers never perform virtualization work directly -- they create
    a Job, enqueue a Celery task, and return {"job_id", "status": "queued"}
    immediately.
    """

    type = models.CharField(max_length=50, choices=JobType.choices)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True)

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="jobs")
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=64, blank=True, default="")
    node = models.ForeignKey("nodes.Node", on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="jobs")

    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=500, blank=True, default="")
    error = models.TextField(blank=True, default="")
    logs = models.JSONField(default=list, blank=True)

    celery_task_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="", db_index=True)
    timeout_seconds = models.PositiveIntegerField(default=600)
    retries = models.PositiveSmallIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["resource_type", "resource_id"]),
            models.Index(fields=["organization", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["created_by", "type", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_job_idempotency_key_per_user_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.type} [{self.status}] {self.resource_type}:{self.resource_id}"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES
