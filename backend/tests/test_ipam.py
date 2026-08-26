import pytest

from apps.networks.models import IPAddressState, Network, Subnet
from apps.networks.services import NoAvailableIPAddress, allocate_ip, find_free_ip, release_ip

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
