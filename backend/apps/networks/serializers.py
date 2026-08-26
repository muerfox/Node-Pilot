from rest_framework import serializers

from apps.networks.models import IPAddress, IPPool, Network, Subnet


class NetworkSerializer(serializers.ModelSerializer):
    node = serializers.SlugRelatedField(slug_field="uuid", queryset=Network._meta.get_field("node").related_model.objects.all())

    class Meta:
        model = Network
        fields = ["uuid", "node", "name", "type", "bridge", "vlan_id", "dhcp_enabled", "status", "created_at"]
        read_only_fields = ["uuid", "status", "created_at"]


class SubnetSerializer(serializers.ModelSerializer):
    network = serializers.SlugRelatedField(slug_field="uuid", queryset=Network.objects.all())

    class Meta:
        model = Subnet
        fields = ["uuid", "network", "cidr", "gateway", "dns_servers", "created_at"]
        read_only_fields = ["uuid", "created_at"]

    def validate_cidr(self, value):
        import ipaddress

        try:
            ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value


class IPPoolSerializer(serializers.ModelSerializer):
    subnet = serializers.SlugRelatedField(slug_field="uuid", queryset=Subnet.objects.all())

    class Meta:
        model = IPPool
        fields = ["uuid", "subnet", "name", "start_address", "end_address"]
        read_only_fields = ["uuid"]


class IPAddressSerializer(serializers.ModelSerializer):
    subnet = serializers.SlugRelatedField(slug_field="uuid", queryset=Subnet.objects.all())

    class Meta:
        model = IPAddress
        fields = ["uuid", "subnet", "address", "state", "note", "created_at"]
        read_only_fields = ["uuid", "state", "created_at"]
