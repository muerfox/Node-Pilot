from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    organization = serializers.SlugRelatedField(slug_field="uuid", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "uuid", "actor", "actor_label", "action", "resource_type", "resource_id",
            "organization", "ip_address", "result", "metadata", "created_at",
        ]
        read_only_fields = fields
