from rest_framework import serializers

from apps.events.models import Event


class EventSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    actor = serializers.SlugRelatedField(slug_field="uuid", read_only=True)

    class Meta:
        model = Event
        fields = ["uuid", "type", "severity", "resource_type", "resource_id", "organization", "actor", "metadata", "created_at"]
        read_only_fields = fields
