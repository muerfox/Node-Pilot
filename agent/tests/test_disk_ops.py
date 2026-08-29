"""disk_ops.py's own logic (independent of which storage backend is
selected) -- specifically that create_disk reports back the *actual*
format the backend produced, not just echoes what was requested. See
test_domain_xml.py and backend/tests/test_disk_format_propagation.py for
the rest of this fix."""
from __future__ import annotations

from unittest.mock import MagicMock

from nodepilot_agent.operations import disk_ops
from nodepilot_agent.storage.base import VolumeInfo


def test_create_disk_returns_the_backends_actual_format(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="vg-data/disk1", size_bytes=1024, format="raw")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    result = disk_ops.create_disk({"storage_type": "LVM", "storage_path": "vg-data", "disk_uuid": "disk1", "size_bytes": 1024, "format": "qcow2"})

    # Requested qcow2, but an LVM backend can only produce raw -- the
    # backend's actual VolumeInfo.format must win in the response.
    assert result["format"] == "raw"
    assert result["volume_id"] == "vg-data/disk1"
    fake_backend.create_volume.assert_called_once_with("disk1", 1024, format="qcow2")


def test_create_disk_reports_qcow2_for_a_directory_backend(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="/pools/local/disk1", size_bytes=1024, format="qcow2")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    result = disk_ops.create_disk({"storage_type": "DIRECTORY", "storage_path": "/pools/local", "disk_uuid": "disk1", "size_bytes": 1024})

    assert result["format"] == "qcow2"
