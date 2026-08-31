"""Builds libvirt domain XML from the CREATE_VM operation payload. Pure
string/XML generation -- no libvirt or subprocess calls here, so it's
trivially unit-testable."""
from __future__ import annotations

from xml.sax.saxutils import escape as _sax_escape

_BUS_DEVICE_PREFIX = {"VIRTIO": "vd", "VIRTIO_SCSI": "sd", "SATA": "sd", "IDE": "hd"}
_BUS_XML_NAME = {"VIRTIO": "virtio", "VIRTIO_SCSI": "scsi", "SATA": "sata", "IDE": "ide"}

# LVM/LVM-thin/ZFS (and, if it's ever wired up, Ceph RBD) volumes are raw
# block devices at a /dev/... path, not regular files -- libvirt needs
# `type="block"` + `<source dev="...">` for those, vs. `type="file"` +
# `<source file="...">` for a qcow2/raw file on a DIRECTORY/NFS pool.
# Getting this wrong (or hardcoding qcow2 as the driver format
# regardless of what the storage backend actually produced) means the
# domain simply won't boot on anything but a DIRECTORY pool.
_BLOCK_BACKED_STORAGE_TYPES = {"LVM", "LVM_THIN", "ZFS", "CEPH_RBD"}


def _resolve_nic_bridge(nic: dict) -> str:
    """A VLAN-tagged network's VM NICs attach to a dedicated per-VLAN
    bridge, never the network's own (uplink) bridge directly -- see
    nodepilot_agent.network.ensure_vlan_network. `vlan_bridge_name` is a
    pure naming function (no subprocess/libvirt calls), so importing it
    here doesn't compromise this module's "no I/O" property."""
    from nodepilot_agent.network import vlan_bridge_name

    bridge = nic.get("bridge", "vmbr0")
    vlan_id = nic.get("vlan")
    return vlan_bridge_name(bridge, vlan_id) if vlan_id else bridge


def _disk_source(disk: dict) -> tuple[str, str, str]:
    """Returns (disk_type_attr, source_element_xml, driver_format) for one
    disk payload dict."""
    is_block = disk.get("storage_type") in _BLOCK_BACKED_STORAGE_TYPES
    volume_id = escape(disk.get("volume_id", ""))
    disk_format = disk.get("format") or ("raw" if is_block else "qcow2")
    if is_block:
        return "block", f'<source dev="{volume_id}"/>', disk_format
    return "file", f'<source file="{volume_id}"/>', disk_format


def escape(value: str) -> str:
    """
    Every value built into this module's XML lands inside a
    double-quoted attribute somewhere (or is safe to over-escape if it
    doesn't). `xml.sax.saxutils.escape`'s default entity set only covers
    `&`/`<`/`>` -- NOT quotes -- so a controller-supplied value containing
    a literal `"` (e.g. a StoragePool.path or Network.bridge an
    org-scoped user can set via the normal API) could break out of an
    attribute and inject arbitrary elements into the domain XML libvirt
    ends up defining. Always escape quotes too.
    """
    return _sax_escape(value, {'"': "&quot;", "'": "&apos;"})


def _next_device_name(prefix: str, index: int) -> str:
    letter = chr(ord("a") + index)
    return f"{prefix}{letter}"


def build_domain_xml(payload: dict) -> str:
    name = escape(payload["name"])
    domain_uuid = payload["domain_uuid"]
    memory_mb = int(payload["memory_mb"])
    cpu = payload.get("cpu", {})
    vcpu = int(cpu.get("count", 1))
    machine_type = payload.get("machine_type", "q35")
    firmware = payload.get("firmware", "BIOS")

    disks_xml = []
    for index, disk in enumerate(payload.get("disks", [])):
        bus = disk.get("bus", "VIRTIO")
        device_name = disk.get("device") or _next_device_name(_BUS_DEVICE_PREFIX.get(bus, "vd"), index)
        discard_attr = ' discard="unmap"' if disk.get("discard") else ""
        readonly_tag = "<readonly/>" if disk.get("readonly") else ""
        disk_type_attr, source_xml, driver_format = _disk_source(disk)
        disks_xml.append(
            f'<disk type="{disk_type_attr}" device="disk">'
            f'<driver name="qemu" type="{driver_format}"{discard_attr}/>'
            f"{source_xml}"
            f'<target dev="{device_name}" bus="{_BUS_XML_NAME.get(bus, "virtio")}"/>'
            f"{readonly_tag}"
            f"</disk>"
        )

    nics_xml = []
    for nic in payload.get("nics", []):
        model = nic.get("model", "VIRTIO").lower()
        bridge = escape(_resolve_nic_bridge(nic))
        mac = escape(nic["mac_address"])
        nics_xml.append(
            f'<interface type="bridge">'
            f'<source bridge="{bridge}"/>'
            f'<mac address="{mac}"/>'
            f'<model type="{model}"/>'
            f"</interface>"
        )

    os_xml = (
        '<os><type arch="x86_64" machine="%s">hvm</type><boot dev="hd"/></os>' % escape(machine_type)
        if firmware == "BIOS"
        else (
            f'<os firmware="efi"><type arch="x86_64" machine="{escape(machine_type)}">hvm</type>'
            f'<boot dev="hd"/></os>'
        )
    )

    return (
        f'<domain type="kvm">'
        f"<name>{name}</name>"
        f"<uuid>{domain_uuid}</uuid>"
        f"<memory unit=\"MiB\">{memory_mb}</memory>"
        f"<currentMemory unit=\"MiB\">{memory_mb}</currentMemory>"
        f'<vcpu placement="static">{vcpu}</vcpu>'
        f"{os_xml}"
        f'<cpu mode="host-passthrough"/>'
        f"<on_poweroff>destroy</on_poweroff>"
        f"<on_reboot>restart</on_reboot>"
        f"<on_crash>restart</on_crash>"
        f"<devices>"
        f'<emulator>/usr/bin/qemu-system-x86_64</emulator>'
        f"{''.join(disks_xml)}"
        f"{''.join(nics_xml)}"
        f'<console type="pty"><target type="serial" port="0"/></console>'
        f'<graphics type="vnc" port="-1" autoport="yes" listen="127.0.0.1"/>'
        f"</devices>"
        f"</domain>"
    )


def build_disk_xml(*, volume_path: str, device: str, bus: str, storage_type: str | None = None, format: str | None = None) -> str:
    disk_type_attr, source_xml, driver_format = _disk_source({"volume_id": volume_path, "storage_type": storage_type, "format": format})
    return (
        f'<disk type="{disk_type_attr}" device="disk">'
        f'<driver name="qemu" type="{driver_format}"/>'
        f"{source_xml}"
        f'<target dev="{escape(device)}" bus="{_BUS_XML_NAME.get(bus, "virtio")}"/>'
        f"</disk>"
    )


def build_cdrom_xml(*, iso_path: str, device: str = "sda") -> str:
    return (
        f'<disk type="file" device="cdrom">'
        f'<driver name="qemu" type="raw"/>'
        f'<source file="{escape(iso_path)}"/>'
        f'<target dev="{escape(device)}" bus="sata"/>'
        f"<readonly/>"
        f"</disk>"
    )


def build_nic_xml(*, bridge: str, mac_address: str, model: str) -> str:
    return (
        f'<interface type="bridge">'
        f'<source bridge="{escape(bridge)}"/>'
        f'<mac address="{escape(mac_address)}"/>'
        f'<model type="{escape(model.lower())}"/>'
        f"</interface>"
    )
