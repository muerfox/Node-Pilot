import pytest
from rest_framework.test import APIClient

from apps.networks.models import IPAddressState, Network, Subnet
from apps.networks.services import InvalidReservation, NoAvailableIPAddress, allocate_ip, find_free_ip, release_ip, reserve_ip
from apps.organizations.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def subnet(node):
    network = Network.objects.create(node=node, name="prod", bridge="vmbr0")
    subnet = Subnet.objects.create(network=network, cidr="10.20.120.0/30", gateway="10.20.120.1")
    subnet.pools.create(start_address="10.20.120.2", end_address="10.20.120.2")  # exactly one usable address
    return subnet


def test_allocate_ip_returns_available_address(subnet):
    ip = allocate_ip(subnet)
    assert ip.address == "10.20.120.2"
    assert ip.state == IPAddressState.ALLOCATED


def test_allocate_ip_exhausts_pool(subnet):
    allocate_ip(subnet)
    with pytest.raises(NoAvailableIPAddress):
        allocate_ip(subnet)


def test_release_ip_makes_it_available_again(subnet):
    ip = allocate_ip(subnet)
    release_ip(ip)
    ip.refresh_from_db()
    assert ip.state == IPAddressState.AVAILABLE

    reallocated = allocate_ip(subnet)
    assert reallocated.address == ip.address


def test_find_free_ip_does_not_allocate(subnet):
    free = find_free_ip(subnet)
    assert free == "10.20.120.2"
    # Calling it again should return the same address -- nothing was consumed.
    assert find_free_ip(subnet) == "10.20.120.2"


# --- reserve_ip -----------------------------------------------------------
#
# reserve_ip existed and was fully implemented but had no caller anywhere
# in the codebase -- not wired into any view, task, or CLI command -- so
# IPAddressState.RESERVED (a first-class model state) was unreachable in
# practice, and the function's collision handling (it used update_or_create
# unconditionally, which would have silently stolen a NIC's live address
# out from under it) had never been exercised.


def test_reserve_ip_marks_the_address_reserved(subnet):
    reserved = reserve_ip(subnet, "10.20.120.1", note="gateway")
    assert reserved.state == IPAddressState.RESERVED
    assert reserved.note == "gateway"


def test_reserve_ip_rejects_an_address_outside_the_subnet(subnet):
    with pytest.raises(InvalidReservation):
        reserve_ip(subnet, "10.20.121.5")


def test_reserve_ip_rejects_an_address_already_allocated_to_a_nic(subnet):
    allocated = allocate_ip(subnet)
    with pytest.raises(InvalidReservation):
        reserve_ip(subnet, allocated.address)
    allocated.refresh_from_db()
    assert allocated.state == IPAddressState.ALLOCATED  # unchanged -- not silently stolen


def test_reserve_ip_is_idempotent_for_an_available_address(subnet):
    reserve_ip(subnet, "10.20.120.1")
    reserved_again = reserve_ip(subnet, "10.20.120.1", note="updated note")
    assert reserved_again.state == IPAddressState.RESERVED
    assert reserved_again.note == "updated note"


def test_allocate_ip_skips_a_reserved_address(subnet):
    reserve_ip(subnet, "10.20.120.2")  # the pool's only address
    with pytest.raises(NoAvailableIPAddress):
        allocate_ip(subnet)


def test_release_ip_also_works_on_a_reserved_address(subnet):
    reserved = reserve_ip(subnet, "10.20.120.1")
    release_ip(reserved)
    reserved.refresh_from_db()
    assert reserved.state == IPAddressState.AVAILABLE


def test_reserve_endpoint_through_the_api(user, organization, node, subnet, grant_permission):
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "network.manage")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(f"/api/v1/subnets/{subnet.uuid}/reserve/", {"address": "10.20.120.1", "note": "gateway"}, format="json")

    assert response.status_code == 201
    assert response.data["state"] == IPAddressState.RESERVED
    assert response.data["address"] == "10.20.120.1"


def test_reserve_endpoint_requires_an_address(user, organization, node, subnet, grant_permission):
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "network.manage")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(f"/api/v1/subnets/{subnet.uuid}/reserve/", {}, format="json")

    assert response.status_code == 400
