from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class ImageType(models.TextChoices):
    ISO = "ISO", "ISO"
    QCOW2 = "QCOW2", "QCOW2"
    RAW = "RAW", "RAW"
    VMDK = "VMDK", "VMDK"


class ImageStatus(models.TextChoices):
    PENDING = "PENDING", "Pending upload"
    UPLOADING = "UPLOADING", "Uploading"
    VERIFYING = "VERIFYING", "Verifying checksum"
    READY = "READY", "Ready"
    FAILED = "FAILED", "Failed"


class Image(NodePilotModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="images")
    storage = models.ForeignKey("storage.StoragePool", on_delete=models.PROTECT, related_name="images")

    name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, blank=True, default="")
    type = models.CharField(max_length=10, choices=ImageType.choices)
    format = models.CharField(max_length=10, blank=True, default="")

    size_bytes = models.BigIntegerField(default=0)
    checksum_algorithm = models.CharField(max_length=20, default="sha256")
    sha256 = models.CharField(max_length=64, blank=True, default="")
    source = models.CharField(max_length=20, default="UPLOAD")
    file_path = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=12, choices=ImageStatus.choices, default=ImageStatus.PENDING)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "images"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} {self.version}".strip()


class UploadStatus(models.TextChoices):
    UPLOADING = "UPLOADING", "Uploading"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    ABORTED = "ABORTED", "Aborted"


class ImageUploadSession(NodePilotModel):
    """
    Resumable/chunked upload session (section 15). Chunks are written
    straight to disk as they arrive -- the image bytes are never fully
    buffered in application memory.
    """

    image = models.OneToOneField(Image, on_delete=models.CASCADE, related_name="upload_session")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    total_size_bytes = models.BigIntegerField()
    received_bytes = models.BigIntegerField(default=0)
    next_chunk_index = models.PositiveIntegerField(default=0)
    expected_sha256 = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=10, choices=UploadStatus.choices, default=UploadStatus.UPLOADING)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "image_upload_sessions"

    def __str__(self) -> str:
        return f"Upload({self.image.name}) {self.received_bytes}/{self.total_size_bytes}"

    @property
    def temp_filename(self) -> str:
        return f"{self.uuid}.part"
