import ipaddress as ip_module

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import NodePilotModel


class NetworkType(models.TextChoices):
    BRIDGE = "BRIDGE", "Linux Bridge"
    VLAN = "VLAN", "VLAN"
    NAT = "NAT", "NAT"
    ROUTED = "ROUTED", "Routed"
    ISOLATED = "ISOLATED", "Isolated"


class NetworkStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    ERROR = "ERROR", "Error"


class Network(NodePilotModel):
    """A network abstraction (section 22) backed by a Linux bridge on a
    node, optionally tagged with a VLAN."""

    node = models.ForeignKey("nodes.Node", on_delete=models.CASCADE, related_name="networks")
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=NetworkType.choices, default=NetworkType.BRIDGE)
    bridge = models.CharField(max_length=32, help_text="e.g. vmbr0")
    vlan_id = models.PositiveIntegerField(null=True, blank=True)
    dhcp_enabled = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=NetworkStatus.choices, default=NetworkStatus.ACTIVE)

    class Meta:
        db_table = "networks"
        unique_together = [("node", "bridge", "vlan_id")]
        ordering = ["node_id", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.bridge}{f'.{self.vlan_id}' if self.vlan_id else ''})"


class Subnet(NodePilotModel):
    """A CIDR block associated with a Network (section 23 IPAM)."""

    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="subnets")
    cidr = models.CharField(max_length=43, help_text="e.g. 10.20.120.0/24")
    gateway = models.GenericIPAddressField(null=True, blank=True)
    dns_servers = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "ipam_subnets"
        unique_together = [("network", "cidr")]

    def __str__(self) -> str:
        return self.cidr

    def clean(self):
        try:
            ip_module.ip_network(self.cidr, strict=True)
        except ValueError as exc:
            raise ValidationError({"cidr": str(exc)}) from exc

    @property
    def network_obj(self) -> ip_module.IPv4Network | ip_module.IPv6Network:
        return ip_module.ip_network(self.cidr, strict=False)


class IPPool(NodePilotModel):
    """A contiguous range within a Subnet reserved for automatic
    allocation (section 23)."""

    subnet = models.ForeignKey(Subnet, on_delete=models.CASCADE, related_name="pools")
    name = models.CharField(max_length=100, blank=True, default="default")
    start_address = models.GenericIPAddressField()
    end_address = models.GenericIPAddressField()

    class Meta:
        db_table = "ipam_pools"

    def __str__(self) -> str:
        return f"{self.subnet.cidr} [{self.start_address}-{self.end_address}]"

    def address_range(self):
        start = int(ip_module.ip_address(self.start_address))
        end = int(ip_module.ip_address(self.end_address))
        for value in range(start, end + 1):
            yield str(ip_module.ip_address(value))


class IPAddressState(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    ALLOCATED = "ALLOCATED", "Allocated"
    RESERVED = "RESERVED", "Reserved"
    BLOCKED = "BLOCKED", "Blocked"


class IPAddress(NodePilotModel):
    subnet = models.ForeignKey(Subnet, on_delete=models.CASCADE, related_name="addresses")
    address = models.GenericIPAddressField()
    state = models.CharField(max_length=10, choices=IPAddressState.choices, default=IPAddressState.AVAILABLE, db_index=True)
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "ipam_addresses"
        unique_together = [("subnet", "address")]
        ordering = ["subnet_id", "address"]

    def __str__(self) -> str:
        return self.address
