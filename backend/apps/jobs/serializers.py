from rest_framework import serializers

from apps.jobs.models import Job


class JobSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    node = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    created_by = serializers.SlugRelatedField(slug_field="uuid", read_only=True)

    class Meta:
        model = Job
        fields = [
            "uuid", "type", "status", "organization", "resource_type", "resource_id",
            "node", "created_by", "progress", "message", "error", "logs",
            "started_at", "finished_at", "created_at",
        ]
        read_only_fields = fields
