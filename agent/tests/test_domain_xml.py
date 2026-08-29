import xml.etree.ElementTree as ET

from nodepilot_agent.domain_xml import build_cdrom_xml, build_domain_xml, build_nic_xml


def test_build_domain_xml_is_well_formed_and_has_expected_shape():
    payload = {
        "domain_uuid": "11111111-1111-1111-1111-111111111111",
        "name": "web-01",
        "memory_mb": 2048,
        "cpu": {"count": 2},
        "firmware": "BIOS",
        "machine_type": "q35",
        "disks": [{"volume_id": "/pool/disk1.qcow2", "bus": "VIRTIO", "device": "vda", "bootable": True}],
        "nics": [{"mac_address": "52:54:00:aa:bb:cc", "model": "VIRTIO", "bridge": "vmbr0"}],
    }
    xml_str = build_domain_xml(payload)
    root = ET.fromstring(xml_str)  # raises if malformed

    assert root.tag == "domain"
    assert root.findtext("name") == "web-01"
    assert root.findtext("uuid") == payload["domain_uuid"]
    assert root.find("memory").text == "2048"
    assert root.find("vcpu").text == "2"

    disk = root.find(".//disk")
    assert disk.find("source").get("file") == "/pool/disk1.qcow2"
    assert disk.find("target").get("dev") == "vda"

    iface = root.find(".//interface")
    assert iface.find("mac").get("address") == "52:54:00:aa:bb:cc"
    assert iface.find("source").get("bridge") == "vmbr0"


def test_build_domain_xml_uefi_firmware():
    payload = {
        "domain_uuid": "22222222-2222-2222-2222-222222222222", "name": "vm", "memory_mb": 1024,
        "cpu": {"count": 1}, "firmware": "UEFI", "machine_type": "q35", "disks": [], "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    assert root.find("os").get("firmware") == "efi"


def test_xml_escaping_prevents_injection_via_name():
    payload = {
        "domain_uuid": "33333333-3333-3333-3333-333333333333",
        "name": '"><script>evil</script>',
        "memory_mb": 512, "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35", "disks": [], "nics": [],
    }
    xml_str = build_domain_xml(payload)
    root = ET.fromstring(xml_str)  # would raise ParseError if the injected text broke the XML structure
    assert root.findtext("name") == '"><script>evil</script>'


def test_build_nic_xml_and_cdrom_xml_are_well_formed():
    ET.fromstring(build_nic_xml(bridge="vmbr0", mac_address="52:54:00:11:22:33", model="VIRTIO"))
    ET.fromstring(build_cdrom_xml(iso_path="/tmp/cloud-init.iso"))


def test_quote_breakout_in_disk_volume_id_cannot_inject_a_sibling_element():
    """A StoragePool.path (or a disk name) containing a literal `"` must
    not be able to close the `source file="..."` attribute early and
    inject a new element -- e.g. a second <disk> exposing an arbitrary
    host path/device to the guest."""
    payload = {
        "domain_uuid": "44444444-4444-4444-4444-444444444444", "name": "vm", "memory_mb": 512,
        "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35",
        "disks": [
            {
                "volume_id": '/pool/x.qcow2"/><disk type="file" device="disk"><source file="/etc/shadow"/>'
                '<target dev="vdz" bus="virtio"/></disk><disk type="file" device="disk"><source file="y',
                "bus": "VIRTIO", "device": "vda",
            }
        ],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))  # raises ParseError if the payload broke out of the attribute
    disks = root.findall(".//disk")
    assert len(disks) == 1  # no smuggled sibling <disk> element -- the payload round-trips as inert attribute text
    assert disks[0].find("source").get("file") == payload["disks"][0]["volume_id"]
    assert disks[0].find("target").get("dev") == "vda"  # our own device name, not the injected "vdz"


def test_quote_breakout_in_bridge_name_cannot_inject_a_sibling_element():
    payload = {
        "domain_uuid": "55555555-5555-5555-5555-555555555555", "name": "vm", "memory_mb": 512,
        "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35", "disks": [],
        "nics": [{"mac_address": "52:54:00:11:22:33", "model": "VIRTIO", "bridge": 'vmbr0"/></interface><hostdev>x'}],
    }
    root = ET.fromstring(build_domain_xml(payload))
    assert len(root.findall(".//interface")) == 1
    assert root.find(".//hostdev") is None


def test_build_nic_xml_escapes_embedded_quote_in_bridge():
    xml_str = build_nic_xml(bridge='vmbr0" x="y', mac_address="52:54:00:11:22:33", model="VIRTIO")
    root = ET.fromstring(xml_str)
    assert root.find("source").get("bridge") == 'vmbr0" x="y'  # round-trips as data, not structure
