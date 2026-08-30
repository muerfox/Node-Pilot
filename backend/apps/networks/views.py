from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.networks.models import IPAddress, IPPool, Network, Subnet
from apps.networks.serializers import IPAddressSerializer, IPPoolSerializer, NetworkSerializer, SubnetSerializer
from apps.networks.services import allocate_ip, release_ip, reserve_ip


class NetworkViewSet(OrganizationScopedModelViewSet):
    queryset = Network.objects.select_related("node", "node__organization").all()
    serializer_class = NetworkSerializer
    organization_field_path = "node__organization"
    permission_map = {
        "list": "network.view", "retrieve": "network.view", "create": "network.manage",
        "update": "network.manage", "partial_update": "network.manage", "destroy": "network.manage",
    }
    filterset_fields = ["node", "type", "status"]
    search_fields = ["name", "bridge"]


class SubnetViewSet(OrganizationScopedModelViewSet):
    queryset = Subnet.objects.select_related("network", "network__node", "network__node__organization").all()
    serializer_class = SubnetSerializer
    organization_field_path = "network__node__organization"
    permission_map = {
        "list": "network.view", "retrieve": "network.view", "create": "network.manage",
        "update": "network.manage", "partial_update": "network.manage", "destroy": "network.manage",
        "allocate": "network.manage", "reserve": "network.manage",
    }
    filterset_fields = ["network"]

    @action(detail=True, methods=["post"])
    def allocate(self, request, uuid=None):
        subnet = self.get_object()
        ip = allocate_ip(subnet, note=request.data.get("note", ""))
        return Response(IPAddressSerializer(ip).data, status=201)

    @action(detail=True, methods=["post"])
    def reserve(self, request, uuid=None):
        """Marks a specific address RESERVED so allocate_ip skips it --
        for addresses that need to stay out of the pool without
        belonging to any VM (a gateway, an externally-managed host)."""
        subnet = self.get_object()
        address = request.data.get("address")
        if not address:
            raise ValidationError({"address": "This field is required."})
        ip = reserve_ip(subnet, address, note=request.data.get("note", ""))
        return Response(IPAddressSerializer(ip).data, status=201)


class IPPoolViewSet(OrganizationScopedModelViewSet):
    queryset = IPPool.objects.select_related("subnet", "subnet__network", "subnet__network__node", "subnet__network__node__organization").all()
    serializer_class = IPPoolSerializer
    organization_field_path = "subnet__network__node__organization"
    permission_map = {
        "list": "network.view", "retrieve": "network.view", "create": "network.manage",
        "update": "network.manage", "partial_update": "network.manage", "destroy": "network.manage",
    }
    filterset_fields = ["subnet"]


class IPAddressViewSet(OrganizationScopedModelViewSet):
    queryset = IPAddress.objects.select_related("subnet", "subnet__network", "subnet__network__node", "subnet__network__node__organization").all()
    serializer_class = IPAddressSerializer
    organization_field_path = "subnet__network__node__organization"
    permission_map = {
        "list": "network.view", "retrieve": "network.view", "create": "network.manage",
        "update": "network.manage", "partial_update": "network.manage", "destroy": "network.manage",
        "release": "network.manage",
    }
    filterset_fields = ["subnet", "state"]
    search_fields = ["address"]

    @action(detail=True, methods=["post"])
    def release(self, request, uuid=None):
        ip = self.get_object()
        release_ip(ip)
        return Response(IPAddressSerializer(ip).data)
