from urllib.parse import urlparse

from rest_framework import serializers

from apps.webhooks.models import SUPPORTED_EVENTS, Webhook, WebhookDelivery
from apps.webhooks.security import is_private_host


class WebhookSerializer(serializers.ModelSerializer):
    """
    Used for list/retrieve/update. The signing secret is masked here --
    someone with webhook.manage listing webhooks should not be able to
    read every webhook's live signing key indefinitely; it's only ever
    shown in full immediately after creation (WebhookCreateSerializer).
    """

    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Webhook._meta.get_field("organization").related_model.objects.all())
    secret = serializers.SerializerMethodField()

    class Meta:
        model = Webhook
        fields = ["uuid", "organization", "name", "url", "secret", "events", "enabled", "created_at"]
        read_only_fields = ["uuid", "secret", "created_at"]

    def get_secret(self, obj: Webhook) -> str:
        return f"{'*' * 8}{obj.secret[-4:]}"

    def validate_url(self, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise serializers.ValidationError("Only http/https webhook URLs are supported.")
        if not parsed.hostname:
            raise serializers.ValidationError("URL must include a hostname.")
        # Best-effort SSRF mitigation (section 46): refuse targets that
        # resolve to private/loopback/link-local address space. This is
        # create-time only and does not by itself defend against DNS
        # rebinding -- `apps.webhooks.tasks.deliver_webhook` re-resolves
        # and pins the address at delivery time for that.
        if is_private_host(parsed.hostname):
            raise serializers.ValidationError("Webhook URL must not target a private, loopback, or link-local address.")
        return value

    def validate_events(self, value: list[str]) -> list[str]:
        if value != ["*"]:
            unknown = set(value) - set(SUPPORTED_EVENTS)
            if unknown:
                raise serializers.ValidationError(f"Unsupported event types: {sorted(unknown)}")
        return value


class WebhookCreateSerializer(WebhookSerializer):
    """Full plaintext secret, shown exactly once in the create response."""

    def get_secret(self, obj: Webhook) -> str:
        return obj.secret


class WebhookDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookDelivery
        fields = ["uuid", "event_type", "status", "attempt", "response_status", "response_body", "delivered_at", "created_at"]
        read_only_fields = fields
