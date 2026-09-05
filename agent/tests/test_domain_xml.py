import xml.etree.ElementTree as ET

from nodepilot_agent.domain_xml import build_cdrom_xml, build_disk_xml, build_domain_xml, build_nic_xml


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


def test_directory_backed_disk_uses_file_type_and_requested_format():
    payload = {
        "domain_uuid": "66666666-6666-6666-6666-666666666666", "name": "vm", "memory_mb": 512,
        "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35",
        "disks": [{"volume_id": "/pools/local/disk.qcow2", "bus": "VIRTIO", "device": "vda", "storage_type": "DIRECTORY", "format": "qcow2"}],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    disk = root.find(".//disk")
    assert disk.get("type") == "file"
    assert disk.find("source").get("file") == "/pools/local/disk.qcow2"
    assert disk.find("source").get("dev") is None
    assert disk.find("driver").get("type") == "qcow2"


def test_lvm_backed_disk_uses_block_type_and_raw_format_even_if_qcow2_was_requested():
    """LVM/LVM-thin/ZFS volumes are raw block devices -- the domain XML
    must say so regardless of what format was originally requested when
    the disk was created (a storage backend that can't do qcow2 always
    wins; see agent's disk_ops.create_disk / backend's
    apps.virtual_machines.tasks provision_vm CREATE_DISK step)."""
    payload = {
        "domain_uuid": "77777777-7777-7777-7777-777777777777", "name": "vm", "memory_mb": 512,
        "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35",
        "disks": [{"volume_id": "vg-data/disk1", "bus": "VIRTIO", "device": "vda", "storage_type": "LVM", "format": "raw"}],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    disk = root.find(".//disk")
    assert disk.get("type") == "block"
    assert disk.find("source").get("dev") == "vg-data/disk1"
    assert disk.find("source").get("file") is None
    assert disk.find("driver").get("type") == "raw"


def test_zfs_and_lvm_thin_are_also_treated_as_block_backed():
    for storage_type in ("ZFS", "LVM_THIN"):
        payload = {
            "domain_uuid": "88888888-8888-8888-8888-888888888888", "name": "vm", "memory_mb": 512,
            "cpu": {"count": 1}, "firmware": "BIOS", "machine_type": "q35",
            "disks": [{"volume_id": "pool/disk", "bus": "VIRTIO", "device": "vda", "storage_type": storage_type}],
            "nics": [],
        }
        root = ET.fromstring(build_domain_xml(payload))
        disk = root.find(".//disk")
        assert disk.get("type") == "block", storage_type
        assert disk.find("driver").get("type") == "raw", storage_type  # defaulted even with no explicit "format"


def test_build_disk_xml_respects_storage_type_and_format_for_attach_detach():
    xml_str = build_disk_xml(volume_path="vg-data/disk1", device="vdb", bus="VIRTIO", storage_type="LVM", format="raw")
    root = ET.fromstring(xml_str)
    assert root.get("type") == "block"
    assert root.find("source").get("dev") == "vg-data/disk1"
    assert root.find("driver").get("type") == "raw"


def test_build_disk_xml_defaults_to_file_type_when_storage_type_omitted():
    """Backward compatible with callers that don't know about
    storage_type -- defaults to the original file/qcow2 behavior."""
    xml_str = build_disk_xml(volume_path="/pools/local/disk.qcow2", device="vdb", bus="VIRTIO")
    root = ET.fromstring(xml_str)
    assert root.get("type") == "file"
    assert root.find("source").get("file") == "/pools/local/disk.qcow2"
    assert root.find("driver").get("type") == "qcow2"


# --- NIC bandwidth (VMNic.rate_limit_mbps was set via the API but never
# read anywhere in domain XML generation -- a configured rate limit was
# silently ignored, giving the VM full unthrottled network access) ------


def test_build_domain_xml_nic_gets_a_bandwidth_element_when_rate_limited():
    xml = build_domain_xml(
        {
            "name": "vm1", "domain_uuid": "11111111-1111-1111-1111-111111111111", "memory_mb": 1024,
            "nics": [{"bridge": "vmbr0", "mac_address": "52:54:00:00:00:01", "rate_limit_mbps": 100}],
        }
    )
    root = ET.fromstring(xml)
    bandwidth = root.find(".//interface/bandwidth")
    assert bandwidth is not None
    # 100 Mbps -> 12500 KiB/s
    assert bandwidth.find("inbound").get("average") == "12500"
    assert bandwidth.find("outbound").get("average") == "12500"


def test_build_domain_xml_nic_has_no_bandwidth_element_when_unset():
    xml = build_domain_xml(
        {
            "name": "vm1", "domain_uuid": "11111111-1111-1111-1111-111111111111", "memory_mb": 1024,
            "nics": [{"bridge": "vmbr0", "mac_address": "52:54:00:00:00:01"}],
        }
    )
    root = ET.fromstring(xml)
    assert root.find(".//interface/bandwidth") is None


def test_build_nic_xml_applies_the_same_rate_limit():
    xml_str = build_nic_xml(bridge="vmbr0", mac_address="52:54:00:00:00:01", model="VIRTIO", rate_limit_mbps=50)
    root = ET.fromstring(xml_str)
    bandwidth = root.find("bandwidth")
    assert bandwidth.find("inbound").get("average") == "6250"  # 50 Mbps -> 6250 KiB/s


def test_build_nic_xml_omits_bandwidth_when_rate_limit_is_none():
    xml_str = build_nic_xml(bridge="vmbr0", mac_address="52:54:00:00:00:01", model="VIRTIO")
    root = ET.fromstring(xml_str)
    assert root.find("bandwidth") is None


# --- iothread and memballoon (VMDisk.iothread / VirtualMachine
# .ballooning_enabled were both user-settable but never read anywhere in
# domain XML generation) ---------------------------------------------


def test_a_disk_with_iothread_gets_a_dedicated_iothread_pool_and_driver_attr():
    payload = {
        "domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024,
        "disks": [{"volume_id": "/pool/disk1.qcow2", "bus": "VIRTIO", "device": "vda", "iothread": True}],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    assert root.findtext("iothreads") == "1"
    driver = root.find(".//disk/driver")
    assert driver.get("iothread") == "1"


def test_a_disk_without_iothread_has_no_pool_declared_or_driver_attr():
    payload = {
        "domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024,
        "disks": [{"volume_id": "/pool/disk1.qcow2", "bus": "VIRTIO", "device": "vda"}],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    assert root.find("iothreads") is None
    driver = root.find(".//disk/driver")
    assert driver.get("iothread") is None


def test_the_iothread_pool_is_declared_once_even_with_multiple_iothread_disks():
    payload = {
        "domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024,
        "disks": [
            {"volume_id": "/pool/disk1.qcow2", "bus": "VIRTIO", "device": "vda", "iothread": True},
            {"volume_id": "/pool/disk2.qcow2", "bus": "VIRTIO", "device": "vdb", "iothread": True},
        ],
        "nics": [],
    }
    root = ET.fromstring(build_domain_xml(payload))
    assert len(root.findall("iothreads")) == 1


def test_ballooning_enabled_gets_a_virtio_memballoon():
    payload = {"domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024, "disks": [], "nics": [], "ballooning_enabled": True}
    root = ET.fromstring(build_domain_xml(payload))
    assert root.find(".//memballoon").get("model") == "virtio"


def test_ballooning_disabled_gets_an_explicit_none_memballoon():
    payload = {"domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024, "disks": [], "nics": [], "ballooning_enabled": False}
    root = ET.fromstring(build_domain_xml(payload))
    assert root.find(".//memballoon").get("model") == "none"


def test_ballooning_defaults_to_enabled_when_omitted():
    payload = {"domain_uuid": "11111111-1111-1111-1111-111111111111", "name": "vm", "memory_mb": 1024, "disks": [], "nics": []}
    root = ET.fromstring(build_domain_xml(payload))
    assert root.find(".//memballoon").get("model") == "virtio"
