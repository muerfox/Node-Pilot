import re

from rest_framework import serializers

from apps.networks.models import IPAddress, IPPool, Network, Subnet

# Mirrors agent/nodepilot_agent/network.py's _SAFE_IFACE -- IFNAMSIZ is 16
# bytes including the NUL, so 15 usable characters. Validating here means
# a bad bridge name is rejected immediately with a clear 400 instead of
# only surfacing once the CREATE_NETWORK job reaches the agent and fails.
_SAFE_IFACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")
_MAX_IFACE_LEN = 15
# A VLAN network additionally needs a dedicated bridge named
# f"{bridge}.{vlan_id}b" (network.vlan_bridge_name) -- the longer of the
# two derived device names, so it's the binding constraint.
_VLAN_BRIDGE_SUFFIX_LEN = len(".4094b")  # worst case: a 4-digit vlan_id


class NetworkSerializer(serializers.ModelSerializer):
    node = serializers.SlugRelatedField(slug_field="uuid", queryset=Network._meta.get_field("node").related_model.objects.all())
    # DRF's ModelSerializer doesn't infer required=False from
    # PositiveIntegerField(null=True, blank=True) the way it does for a
    # blank-able CharField. Worse: vlan_id participates in the model's
    # unique_together ("node", "bridge", "vlan_id"), and DRF's
    # UniqueTogetherValidator.enforce_required_fields() requires every
    # participating field to have an explicit `default` (allow_null alone
    # doesn't count) or it demands the key be present regardless of
    # required=False. Without both required=False *and* default=None, a
    # plain (non-VLAN) network create that simply omits vlan_id (rather
    # than explicitly sending null) was rejected with a spurious "this
    # field is required".
    vlan_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    class Meta:
        model = Network
        fields = ["uuid", "node", "name", "type", "bridge", "vlan_id", "dhcp_enabled", "status", "created_at"]
        read_only_fields = ["uuid", "status", "created_at"]

    def validate_bridge(self, value: str) -> str:
        if not _SAFE_IFACE.match(value):
            raise serializers.ValidationError("Bridge name must be a valid Linux interface name (alphanumeric, '.', '-', '_', max 15 characters).")
        return value

    def validate_vlan_id(self, value: int | None) -> int | None:
        if value is not None and not (1 <= value <= 4094):
            raise serializers.ValidationError("vlan_id must be between 1 and 4094.")
        return value

    def validate(self, attrs: dict) -> dict:
        bridge = attrs.get("bridge", getattr(self.instance, "bridge", ""))
        vlan_id = attrs.get("vlan_id", getattr(self.instance, "vlan_id", None))
        if vlan_id and len(bridge) + _VLAN_BRIDGE_SUFFIX_LEN > _MAX_IFACE_LEN:
            raise serializers.ValidationError({"bridge": f"Bridge name is too long to combine with a VLAN id -- max {_MAX_IFACE_LEN - _VLAN_BRIDGE_SUFFIX_LEN} characters when vlan_id is set."})
        return attrs


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
