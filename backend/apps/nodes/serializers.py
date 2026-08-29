from rest_framework import serializers

from apps.nodes.models import Agent, Node


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = ["uuid", "agent_id", "status", "token_prefix", "protocol_version", "mtls_enabled", "last_heartbeat_at", "registered_at"]
        read_only_fields = fields


class NodeSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Node._meta.get_field("organization").related_model.objects.all())
    status = serializers.SerializerMethodField()
    agent = AgentSerializer(read_only=True)

    class Meta:
        model = Node
        fields = [
            "uuid", "organization", "name", "hostname", "fqdn", "admin_state", "status",
            "agent_version", "kernel", "architecture", "cpu_model", "cpu_threads", "cpu_cores", "cpu_sockets",
            "memory_total_mb", "memory_available_mb", "storage_total_gb", "storage_available_gb",
            "reported_vm_count", "last_seen", "agent", "created_at", "updated_at",
        ]
        read_only_fields = [
            "uuid", "status", "agent_version", "kernel", "architecture", "cpu_model", "cpu_threads", "cpu_cores",
            "cpu_sockets", "memory_total_mb", "memory_available_mb", "storage_total_gb", "storage_available_gb",
            "reported_vm_count", "last_seen", "agent", "created_at", "updated_at",
        ]

    def get_status(self, obj: Node) -> str:
        return obj.effective_status()


class NodeCreateSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Node._meta.get_field("organization").related_model.objects.all())

    class Meta:
        model = Node
        fields = ["uuid", "organization", "name", "hostname", "fqdn"]
        read_only_fields = ["uuid"]


class HeartbeatSerializer(serializers.Serializer):
    agent_version = serializers.CharField()
    protocol_version = serializers.CharField(required=False, default="1.0")
    timestamp = serializers.DateTimeField(required=False)
    kernel = serializers.CharField(required=False, allow_blank=True, default="")
    architecture = serializers.CharField(required=False, allow_blank=True, default="")
    cpu = serializers.DictField(required=False, default=dict)
    memory = serializers.DictField(required=False, default=dict)
    storage = serializers.DictField(required=False, default=dict)
    vms = serializers.IntegerField(required=False, default=0)


class VMMetricSampleSerializer(serializers.Serializer):
    domain_uuid = serializers.UUIDField()
    cpu_percent = serializers.FloatField(required=False, allow_null=True, default=None)
    memory_used_mb = serializers.IntegerField(required=False, allow_null=True, default=None)


class VMMetricsBatchSerializer(serializers.Serializer):
    samples = VMMetricSampleSerializer(many=True)
