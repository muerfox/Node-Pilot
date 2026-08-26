from rest_framework import serializers

from apps.images.models import Image
from apps.networks.models import Network
from apps.nodes.models import Node
from apps.organizations.models import Project
from apps.storage.models import StoragePool
from apps.vm_templates.models import Template


class TemplateSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Template._meta.get_field("organization").related_model.objects.all())
    image = serializers.SlugRelatedField(slug_field="uuid", queryset=Image.objects.all())

    class Meta:
        model = Template
        fields = [
            "uuid", "organization", "image", "name", "description", "default_cpu_count", "default_memory_mb",
            "default_disk_gb", "default_firmware", "default_os_type", "network_defaults", "cloud_init_defaults",
            "is_active", "created_at",
        ]
        read_only_fields = ["uuid", "created_at"]


class DeployTemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    project = serializers.SlugRelatedField(slug_field="uuid", queryset=Project.objects.all())
    node = serializers.SlugRelatedField(slug_field="uuid", queryset=Node.objects.all(), required=False, allow_null=True)
    storage = serializers.SlugRelatedField(slug_field="uuid", queryset=StoragePool.objects.all())
    network = serializers.SlugRelatedField(slug_field="uuid", queryset=Network.objects.all())
    cpu_count = serializers.IntegerField(required=False, min_value=1)
    memory_mb = serializers.IntegerField(required=False, min_value=128)
    disk_gb = serializers.IntegerField(required=False, min_value=1)
    autostart = serializers.BooleanField(default=True)
