from rest_framework import serializers

from apps.snapshots.models import Snapshot
from apps.virtual_machines.models import VirtualMachine


class SnapshotSerializer(serializers.ModelSerializer):
    vm = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine.objects.all())

    class Meta:
        model = Snapshot
        fields = ["uuid", "vm", "name", "description", "status", "size_bytes", "created_at"]
        read_only_fields = ["uuid", "status", "size_bytes", "created_at"]
