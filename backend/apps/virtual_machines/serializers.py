from rest_framework import serializers

from apps.networks.models import Network
from apps.storage.models import StoragePool
from apps.virtual_machines.models import VirtualMachine, VMDisk, VMNic


class VMDiskSerializer(serializers.ModelSerializer):
    storage = serializers.SlugRelatedField(slug_field="uuid", queryset=StoragePool.objects.all())

    class Meta:
        model = VMDisk
        fields = ["uuid", "storage", "name", "volume_id", "bus", "device", "size_bytes", "format", "bootable", "readonly", "discard", "iothread", "boot_index"]
        read_only_fields = ["uuid", "volume_id", "device"]


class VMNicSerializer(serializers.ModelSerializer):
    network = serializers.SlugRelatedField(slug_field="uuid", queryset=Network.objects.all())

    class Meta:
        model = VMNic
        fields = ["uuid", "network", "mac_address", "model", "vlan", "rate_limit_mbps", "bootable", "boot_index", "ip_address"]
        read_only_fields = ["uuid", "mac_address", "ip_address"]


class VirtualMachineSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    project = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    node = serializers.SlugRelatedField(slug_field="uuid", read_only=True)
    disks = VMDiskSerializer(many=True, read_only=True)
    nics = VMNicSerializer(many=True, read_only=True)

    class Meta:
        model = VirtualMachine
        fields = [
            "uuid", "name", "hostname", "description", "organization", "project", "node",
            "status", "provisioning_state", "os_type", "firmware", "machine_type",
            "cpu_count", "cpu_sockets", "cpu_cores", "cpu_threads", "cpu_model",
            "memory_mb", "min_memory_mb", "max_memory_mb", "ballooning_enabled",
            "boot_order", "autostart", "cloud_init_enabled", "disks", "nics",
            "last_error", "created_at", "updated_at",
        ]
        read_only_fields = [f for f in fields if f not in {"name", "hostname", "description", "boot_order", "autostart"}]


class VMDiskCreateSerializer(serializers.Serializer):
    storage = serializers.SlugRelatedField(slug_field="uuid", queryset=StoragePool.objects.all())
    name = serializers.CharField(required=False)
    size_gb = serializers.IntegerField(min_value=1)
    bus = serializers.ChoiceField(choices=["VIRTIO", "VIRTIO_SCSI", "SATA", "IDE"], default="VIRTIO")
    bootable = serializers.BooleanField(default=False)
    format = serializers.ChoiceField(choices=["qcow2", "raw"], default="qcow2")


class VMNicCreateSerializer(serializers.Serializer):
    network = serializers.SlugRelatedField(slug_field="uuid", queryset=Network.objects.all())
    model = serializers.ChoiceField(choices=["VIRTIO", "E1000"], default="VIRTIO")
    vlan = serializers.IntegerField(required=False, allow_null=True)
    mac_address = serializers.CharField(required=False, allow_blank=True)
    bootable = serializers.BooleanField(default=False)
    rate_limit_mbps = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class VirtualMachineCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    project = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine._meta.get_field("project").related_model.objects.all())
    node = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine._meta.get_field("node").related_model.objects.all(), required=False, allow_null=True)
    template = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine._meta.get_field("template").related_model.objects.all(), required=False, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    os_type = serializers.CharField(required=False, default="linux")
    firmware = serializers.ChoiceField(choices=["BIOS", "UEFI"], default="BIOS")
    cpu_count = serializers.IntegerField(min_value=1, max_value=256, default=1)
    memory_mb = serializers.IntegerField(min_value=128, default=2048)
    disks = VMDiskCreateSerializer(many=True, required=False)
    nics = VMNicCreateSerializer(many=True, required=False)
    cloud_init_enabled = serializers.BooleanField(default=False)
    cloud_init_config = serializers.DictField(required=False, default=dict)
    autostart = serializers.BooleanField(default=True)

    def validate(self, attrs):
        project = attrs["project"]
        request = self.context["request"]
        organization = self._organization(request)
        if organization is None or project.organization_id != organization.pk:
            raise serializers.ValidationError({"project": "Project does not belong to the target organization."})
        return attrs

    def _organization(self, request):
        org_id = request.query_params.get("organization") or request.data.get("organization")
        if not org_id:
            return None
        from apps.organizations.models import Organization

        return Organization.objects.filter(uuid=org_id).first()
