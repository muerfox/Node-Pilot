import secrets

from django.db import models

from apps.common.models import NodePilotModel

# section 37
SUPPORTED_EVENTS = [
    "vm.created", "vm.started", "vm.stopped", "vm.deleted", "vm.cloned",
    "backup.completed", "backup.failed", "node.offline", "node.online",
]


class Webhook(NodePilotModel):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="webhooks")
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=64, editable=False)
    events = models.JSONField(default=list, blank=True, help_text='Subscribed event types, or ["*"] for all.')
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "webhooks"

    def __str__(self) -> str:
        return f"{self.name} -> {self.url}"

    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def subscribes_to(self, event_type: str) -> bool:
        return self.enabled and ("*" in self.events or event_type in self.events)


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"
    RETRYING = "RETRYING", "Retrying"


class WebhookDelivery(NodePilotModel):
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name="deliveries")
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    attempt = models.PositiveSmallIntegerField(default=0)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhook_deliveries"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.webhook.name}:{self.event_type} [{self.status}]"
