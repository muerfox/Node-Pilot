"""Builds libvirt domain XML from the CREATE_VM operation payload. Pure
string/XML generation -- no libvirt or subprocess calls here, so it's
trivially unit-testable."""
from __future__ import annotations

from xml.sax.saxutils import escape

_BUS_DEVICE_PREFIX = {"VIRTIO": "vd", "VIRTIO_SCSI": "sd", "SATA": "sd", "IDE": "hd"}
_BUS_XML_NAME = {"VIRTIO": "virtio", "VIRTIO_SCSI": "scsi", "SATA": "sata", "IDE": "ide"}


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
        disks_xml.append(
            f'<disk type="file" device="disk">'
            f'<driver name="qemu" type="qcow2"{discard_attr}/>'
            f'<source file="{escape(disk.get("volume_id", ""))}"/>'
            f'<target dev="{device_name}" bus="{_BUS_XML_NAME.get(bus, "virtio")}"/>'
            f"{readonly_tag}"
            f"</disk>"
        )

    nics_xml = []
    for nic in payload.get("nics", []):
        model = nic.get("model", "VIRTIO").lower()
        bridge = escape(nic.get("bridge", "vmbr0"))
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


def build_disk_xml(*, volume_path: str, device: str, bus: str) -> str:
    return (
        f'<disk type="file" device="disk">'
        f'<driver name="qemu" type="qcow2"/>'
        f'<source file="{escape(volume_path)}"/>'
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
