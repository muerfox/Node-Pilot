import ipaddress
import socket
from urllib.parse import urlparse

from rest_framework import serializers

from apps.webhooks.models import SUPPORTED_EVENTS, Webhook, WebhookDelivery


def _is_private_host(hostname: str) -> bool:
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        pass  # Not a literal IP; resolve it.
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except socket.gaierror:
        return True  # Can't resolve it -- reject rather than risk surprises.
    return False


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
        # resolve to private/loopback/link-local address space. This does
        # not defend against DNS rebinding between validation and delivery
        # time; a production deployment should additionally pin resolved
        # addresses at request time or route webhook egress through an
        # isolated network path.
        if _is_private_host(parsed.hostname):
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
