from __future__ import annotations

from nodepilot_agent import network
from nodepilot_agent.libvirt_client import LibvirtClient


def create_network(payload: dict) -> dict:
    """Returns the bridge VM NICs should actually attach to. For a
    VLAN-tagged network that's a dedicated bridge distinct from
    `payload["bridge"]` (see network.ensure_vlan_network) -- for a plain
    bridge network it's `payload["bridge"]` itself."""
    bridge = payload["bridge"]
    vlan_id = payload.get("vlan_id")
    if vlan_id:
        return {"bridge": network.ensure_vlan_network(bridge, vlan_id)}
    network.create_bridge(bridge)
    return {"bridge": bridge}


def delete_network(payload: dict) -> dict:
    vlan_id = payload.get("vlan_id")
    if vlan_id:
        network.teardown_vlan_network(payload["bridge"], vlan_id)
    else:
        network.delete_bridge(payload["bridge"])
    return {}


def _nic_target_bridge(payload: dict) -> str:
    """A NIC's `vlan` (defaulting to its network's vlan_id, resolved by
    the controller) picks which of that parent bridge's VLAN-dedicated
    bridges to attach to -- see network.ensure_vlan_network. Attaching
    to a vlan that was never provisioned via CREATE_NETWORK fails with a
    clear libvirt "no such device" error rather than silently landing on
    the wrong (untagged) segment."""
    bridge = payload["bridge"]
    vlan_id = payload.get("vlan")
    return network.vlan_bridge_name(bridge, vlan_id) if vlan_id else bridge


def attach_nic(payload: dict, libvirt_client: LibvirtClient) -> dict:
    from nodepilot_agent.domain_xml import build_nic_xml

    xml = build_nic_xml(bridge=_nic_target_bridge(payload), mac_address=payload["mac_address"], model=payload.get("model", "VIRTIO"))
    libvirt_client.attach_device(payload["domain_uuid"], xml)
    return {}


def detach_nic(payload: dict, libvirt_client: LibvirtClient) -> dict:
    from nodepilot_agent.domain_xml import build_nic_xml

    xml = build_nic_xml(bridge=_nic_target_bridge(payload), mac_address=payload["mac_address"], model=payload.get("model", "VIRTIO"))
    libvirt_client.detach_device(payload["domain_uuid"], xml)
    return {}
