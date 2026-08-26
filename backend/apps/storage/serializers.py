from rest_framework import serializers

from apps.storage.models import StoragePool


class StoragePoolSerializer(serializers.ModelSerializer):
    node = serializers.SlugRelatedField(slug_field="uuid", queryset=StoragePool._meta.get_field("node").related_model.objects.all())

    class Meta:
        model = StoragePool
        fields = [
            "uuid", "node", "name", "type", "path", "capacity_bytes", "used_bytes", "available_bytes",
            "status", "shared", "enabled", "capabilities", "created_at", "updated_at",
        ]
        read_only_fields = ["uuid", "capacity_bytes", "used_bytes", "available_bytes", "status", "created_at", "updated_at"]
