from __future__ import annotations

import os

from nodepilot_agent.cloud_init import generate_nocloud_iso
from nodepilot_agent.domain_xml import build_cdrom_xml
from nodepilot_agent.libvirt_client import LibvirtClient


def generate_cloud_init(payload: dict, resource_id: str, workdir: str, libvirt_client: LibvirtClient) -> dict:
    os.makedirs(workdir, exist_ok=True)
    iso_path = os.path.join(workdir, f"{resource_id}.iso")
    generate_nocloud_iso(payload.get("cloud_init", {}), iso_path)

    xml = build_cdrom_xml(iso_path=iso_path)
    libvirt_client.attach_device(resource_id, xml, live=False, persistent=True)
    return {"iso_path": iso_path}
