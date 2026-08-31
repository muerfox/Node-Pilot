"""
Network provisioning (section 22) and IPAM allocation (section 23).
Address rows are created lazily as they are first touched rather than
pre-materializing an entire subnet, but allocation itself is serialized
per-subnet with a Redis lock so two concurrent VM provisions can never be
handed the same address.
"""
from __future__ import annotations

from django.db import transaction

from apps.common.exceptions import NodePilotAPIException
from apps.common.locks import RedisLock
from apps.jobs.models import JobType
from apps.jobs.services import create_job
from apps.networks.models import IPAddress, IPAddressState, IPPool, Network, NetworkStatus, Subnet


class NoAvailableIPAddress(NodePilotAPIException):
    code_name = "NO_AVAILABLE_IP_ADDRESS"
    status_code = 409
    default_detail = "No available IP address in the requested subnet/pool."


class InvalidReservation(NodePilotAPIException):
    code_name = "INVALID_IP_RESERVATION"
    status_code = 409


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
    """Marks `address` RESERVED so `allocate_ip` will never hand it out --
    for addresses that need to stay out of the pool without belonging to
    any VM's NIC (a gateway, an externally-managed host, ...)."""
    import ipaddress as ip_module

    try:
        parsed = ip_module.ip_address(address)
    except ValueError as exc:
        raise InvalidReservation(f"{address!r} is not a valid IP address.") from exc
    if parsed not in subnet.network_obj:
        raise InvalidReservation(f"{address} is not within subnet {subnet.cidr}.")

    with _subnet_lock(subnet):
        existing = IPAddress.objects.filter(subnet=subnet, address=address).first()
        if existing is not None and existing.state == IPAddressState.ALLOCATED:
            raise InvalidReservation(f"{address} is already allocated to a NIC; release it before reserving it.")
        obj, _ = IPAddress.objects.update_or_create(subnet=subnet, address=address, defaults={"state": IPAddressState.RESERVED, "note": note})
        return obj


def find_free_ip(subnet: Subnet) -> str | None:
    for candidate_pool in subnet.pools.all():
        for address in candidate_pool.address_range():
            existing = IPAddress.objects.filter(subnet=subnet, address=address).first()
            if existing is None or existing.state == IPAddressState.AVAILABLE:
                return address
    return None


def create_network(*, node, name: str, type: str, bridge: str, vlan_id: int | None, dhcp_enabled: bool, requested_by) -> tuple[Network, "Job"]:
    """Creates the Network row (status INACTIVE until the agent confirms
    the bridge -- and, for a VLAN network, its dedicated per-VLAN bridge
    plus tagged uplink -- actually exists) and dispatches CREATE_NETWORK.
    The HTTP handler never blocks on the actual provisioning (rule 4/5)."""
    network = Network.objects.create(
        node=node, name=name, type=type, bridge=bridge, vlan_id=vlan_id, dhcp_enabled=dhcp_enabled, status=NetworkStatus.INACTIVE,
    )
    job = create_job(type=JobType.NETWORK_CREATE, resource_type="Network", resource_id=str(network.uuid), organization=node.organization, node=node, created_by=requested_by)
    transaction.on_commit(lambda: _enqueue_create_network(job.pk, network.pk))
    return network, job


def delete_network(network: Network, requested_by) -> "Job":
    """Dispatches DELETE_NETWORK; the Network row itself is only removed
    once the agent confirms the bridge (and any VLAN uplink) is actually
    torn down -- see apps.networks.tasks.delete_network_task. Until then
    it's left visible with its current status so a failed teardown isn't
    silently reported as done."""
    job = create_job(
        type=JobType.NETWORK_DELETE, resource_type="Network", resource_id=str(network.uuid),
        organization=network.node.organization, node=network.node, created_by=requested_by,
    )
    transaction.on_commit(lambda: _enqueue_delete_network(job.pk, network.pk))
    return job


def _enqueue_create_network(job_id: int, network_id: int) -> None:
    from apps.networks.tasks import create_network_task

    create_network_task.delay(job_id, network_id)


def _enqueue_delete_network(job_id: int, network_id: int) -> None:
    from apps.networks.tasks import delete_network_task

    delete_network_task.delay(job_id, network_id)
