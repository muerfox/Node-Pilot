from __future__ import annotations

from nodepilot_agent import network
from nodepilot_agent.libvirt_client import LibvirtClient


def create_network(payload: dict) -> dict:
    bridge = payload["bridge"]
    network.create_bridge(bridge)
    if payload.get("vlan_id"):
        network.create_vlan_interface(payload.get("parent_iface", bridge), payload["vlan_id"])
    return {"bridge": bridge}


def delete_network(payload: dict) -> dict:
    if payload.get("vlan_id"):
        network.delete_vlan_interface(payload.get("parent_iface", payload["bridge"]), payload["vlan_id"])
    else:
        network.delete_bridge(payload["bridge"])
    return {}


def attach_nic(payload: dict, libvirt_client: LibvirtClient) -> dict:
    from nodepilot_agent.domain_xml import build_nic_xml

    xml = build_nic_xml(bridge=payload["bridge"], mac_address=payload["mac_address"], model=payload.get("model", "VIRTIO"))
    libvirt_client.attach_device(payload["domain_uuid"], xml)
    return {}


def detach_nic(payload: dict, libvirt_client: LibvirtClient) -> dict:
    from nodepilot_agent.domain_xml import build_nic_xml

    xml = build_nic_xml(bridge=payload["bridge"], mac_address=payload["mac_address"], model=payload.get("model", "VIRTIO"))
    libvirt_client.detach_device(payload["domain_uuid"], xml)
    return {}
