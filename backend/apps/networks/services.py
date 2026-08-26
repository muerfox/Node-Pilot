"""
IPAM allocation (section 23). Address rows are created lazily as they are
first touched rather than pre-materializing an entire subnet, but
allocation itself is serialized per-subnet with a Redis lock so two
concurrent VM provisions can never be handed the same address.
"""
from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import NodePilotAPIException
from apps.common.locks import RedisLock
from apps.networks.models import IPAddress, IPAddressState, IPPool, Subnet


class NoAvailableIPAddress(NodePilotAPIException):
    code_name = "NO_AVAILABLE_IP_ADDRESS"
    status_code = 409
    default_detail = "No available IP address in the requested subnet/pool."


def _subnet_lock(subnet: Subnet) -> RedisLock:
    return RedisLock(f"subnet:{subnet.pk}:ipam", ttl_seconds=15)


@transaction.atomic
def allocate_ip(subnet: Subnet, *, pool: IPPool | None = None, note: str = "") -> IPAddress:
    with _subnet_lock(subnet):
        pools = [pool] if pool else list(subnet.pools.all())
        if not pools:
            raise NoAvailableIPAddress("Subnet has no configured IP pool to allocate from.")

        for candidate_pool in pools:
            for address in candidate_pool.address_range():
                existing = IPAddress.objects.select_for_update().filter(subnet=subnet, address=address).first()
                if existing is None:
                    return IPAddress.objects.create(subnet=subnet, address=address, state=IPAddressState.ALLOCATED, note=note)
                if existing.state == IPAddressState.AVAILABLE:
                    existing.state = IPAddressState.ALLOCATED
                    existing.note = note
                    existing.save(update_fields=["state", "note"])
                    return existing
        raise NoAvailableIPAddress(f"No available address in {subnet.cidr}.")


def release_ip(ip_address: IPAddress) -> None:
    ip_address.state = IPAddressState.AVAILABLE
    ip_address.note = ""
    ip_address.save(update_fields=["state", "note"])


def reserve_ip(subnet: Subnet, address: str, note: str = "") -> IPAddress:
    obj, _ = IPAddress.objects.update_or_create(subnet=subnet, address=address, defaults={"state": IPAddressState.RESERVED, "note": note})
    return obj


def find_free_ip(subnet: Subnet) -> str | None:
    for candidate_pool in subnet.pools.all():
        for address in candidate_pool.address_range():
            existing = IPAddress.objects.filter(subnet=subnet, address=address).first()
            if existing is None or existing.state == IPAddressState.AVAILABLE:
                return address
    return None
