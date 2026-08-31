"""
apps.networks never dispatched CREATE_NETWORK/DELETE_NETWORK from the
backend at all before this fix (see backend/tests/test_network_provisioning.py),
so these agent-side handlers had zero test coverage despite being fully
implemented -- exactly the kind of gap that predicted real bugs earlier
this session.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nodepilot_agent.operations import network_ops


@pytest.fixture
def fake_ensure_vlan_network(monkeypatch):
    calls = []

    def fake(parent_bridge, vlan_id):
        calls.append((parent_bridge, vlan_id))
        return f"{parent_bridge}.{vlan_id}b"

    monkeypatch.setattr(network_ops.network, "ensure_vlan_network", fake)
    return calls


@pytest.fixture
def fake_teardown_vlan_network(monkeypatch):
    calls = []
    monkeypatch.setattr(network_ops.network, "teardown_vlan_network", lambda p, v: calls.append((p, v)))
    return calls


@pytest.fixture
def fake_create_bridge(monkeypatch):
    calls = []
    monkeypatch.setattr(network_ops.network, "create_bridge", lambda name: calls.append(name))
    return calls


@pytest.fixture
def fake_delete_bridge(monkeypatch):
    calls = []
    monkeypatch.setattr(network_ops.network, "delete_bridge", lambda name: calls.append(name))
    return calls


def test_create_network_without_vlan_just_creates_the_plain_bridge(fake_create_bridge, fake_ensure_vlan_network):
    result = network_ops.create_network({"bridge": "vmbr0"})

    assert result == {"bridge": "vmbr0"}
    assert fake_create_bridge == ["vmbr0"]
    assert fake_ensure_vlan_network == []


def test_create_network_with_vlan_provisions_the_dedicated_bridge(fake_create_bridge, fake_ensure_vlan_network):
    result = network_ops.create_network({"bridge": "vmbr0", "vlan_id": 120})

    assert result == {"bridge": "vmbr0.120b"}
    assert fake_ensure_vlan_network == [("vmbr0", 120)]
    assert fake_create_bridge == []  # ensure_vlan_network handles bridge creation itself


def test_delete_network_without_vlan_deletes_the_plain_bridge(fake_delete_bridge, fake_teardown_vlan_network):
    network_ops.delete_network({"bridge": "vmbr0"})

    assert fake_delete_bridge == ["vmbr0"]
    assert fake_teardown_vlan_network == []


def test_delete_network_with_vlan_tears_down_the_vlan_network(fake_delete_bridge, fake_teardown_vlan_network):
    network_ops.delete_network({"bridge": "vmbr0", "vlan_id": 120})

    assert fake_teardown_vlan_network == [("vmbr0", 120)]
    assert fake_delete_bridge == []


def test_attach_nic_targets_the_dedicated_vlan_bridge():
    libvirt_client = MagicMock()
    network_ops.attach_nic({"domain_uuid": "vm-1", "bridge": "vmbr0", "vlan": 120, "mac_address": "52:54:00:00:00:01"}, libvirt_client)

    xml = libvirt_client.attach_device.call_args.args[1]
    assert 'source bridge="vmbr0.120b"' in xml


def test_attach_nic_targets_the_raw_bridge_when_there_is_no_vlan():
    libvirt_client = MagicMock()
    network_ops.attach_nic({"domain_uuid": "vm-1", "bridge": "vmbr0", "mac_address": "52:54:00:00:00:01"}, libvirt_client)

    xml = libvirt_client.attach_device.call_args.args[1]
    assert 'source bridge="vmbr0"' in xml


def test_detach_nic_targets_the_same_dedicated_bridge_attach_used():
    """Detaching with the wrong bridge name in <source> means libvirt
    won't match the device to remove -- attach and detach must resolve
    identically."""
    libvirt_client = MagicMock()
    payload = {"domain_uuid": "vm-1", "bridge": "vmbr0", "vlan": 120, "mac_address": "52:54:00:00:00:01"}

    network_ops.attach_nic(payload, libvirt_client)
    network_ops.detach_nic(payload, libvirt_client)

    attach_xml = libvirt_client.attach_device.call_args.args[1]
    detach_xml = libvirt_client.detach_device.call_args.args[1]
    assert attach_xml == detach_xml
