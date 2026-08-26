import pytest

from nodepilot_agent.network import NetworkOperationError, _validate_iface, vlan_interface_name


def test_valid_interface_name_passes():
    assert _validate_iface("vmbr0") == "vmbr0"


@pytest.mark.parametrize("bad_name", ["", "a" * 20, "vmbr0; rm -rf /", "../etc", "vm br0"])
def test_invalid_interface_name_rejected(bad_name):
    with pytest.raises(NetworkOperationError):
        _validate_iface(bad_name)


def test_vlan_interface_name_format():
    assert vlan_interface_name("vmbr0", 120) == "vmbr0.120"
