"""disk_ops.py's own logic (independent of which storage backend is
selected) -- specifically that create_disk reports back the *actual*
format the backend produced, not just echoes what was requested. See
test_domain_xml.py and backend/tests/test_disk_format_propagation.py for
the rest of this fix.

Also covers the image-seeding path added to close a real gap: deploying
a VM from a Template used to produce a completely blank disk since
Template.image was never referenced anywhere in provisioning."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from nodepilot_agent import image_fetch
from nodepilot_agent.operations import disk_ops
from nodepilot_agent.storage.base import StorageOperationError, VolumeInfo


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


# --- image-seeding (deploy from Template) --------------------------------


class _FakeConfig:
    controller_url = "https://controller.example"
    agent_token = "test-agent-token"
    tls_verify = True


def _fake_downloaded_file(content: bytes = b"fake image bytes") -> str:
    tmp_dir = tempfile.mkdtemp(prefix="test-download-")
    path = os.path.join(tmp_dir, "image")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def test_create_disk_seeds_from_the_image_when_one_is_specified(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="/pools/local/disk1", size_bytes=20 * 1024**3, format="qcow2")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    downloaded_path = _fake_downloaded_file()
    monkeypatch.setattr(image_fetch, "download_image", lambda config, image_uuid, expected_sha256="": downloaded_path)

    run_calls = []
    monkeypatch.setattr(disk_ops, "run", lambda args, **kwargs: run_calls.append(args))

    payload = {
        "storage_type": "DIRECTORY", "storage_path": "/pools/local", "disk_uuid": "disk1", "size_bytes": 20 * 1024**3,
        "image_uuid": "img-1", "image_format": "raw", "image_sha256": "abc123",
    }
    result = disk_ops.create_disk(payload, config=_FakeConfig())

    assert result["volume_id"] == "/pools/local/disk1"
    assert len(run_calls) == 1
    args = run_calls[0]
    assert args[:3] == ["qemu-img", "convert", "-n"]
    assert "-f" in args and args[args.index("-f") + 1] == "raw"  # source format, from the image's own metadata
    assert "-O" in args and args[args.index("-O") + 1] == "qcow2"  # target format -- what create_volume actually produced
    assert args[-2:] == [downloaded_path, "/pools/local/disk1"]
    assert not os.path.exists(downloaded_path)  # temp download cleaned up afterward


def test_create_disk_without_an_image_never_touches_image_fetch(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="/pools/local/disk1", size_bytes=1024, format="qcow2")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    def boom(*args, **kwargs):
        raise AssertionError("download_image should not be called for a plain (non-templated) disk")

    monkeypatch.setattr(image_fetch, "download_image", boom)

    result = disk_ops.create_disk({"storage_type": "DIRECTORY", "storage_path": "/pools/local", "disk_uuid": "disk1", "size_bytes": 1024})
    assert result["volume_id"] == "/pools/local/disk1"


def test_create_disk_requires_config_to_seed_from_an_image(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="/pools/local/disk1", size_bytes=1024, format="qcow2")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    with pytest.raises(StorageOperationError, match="no agent config"):
        disk_ops.create_disk({"storage_type": "DIRECTORY", "storage_path": "/pools/local", "disk_uuid": "disk1", "size_bytes": 1024, "image_uuid": "img-1"})


def test_create_disk_cleans_up_the_download_even_if_qemu_img_fails(monkeypatch):
    fake_backend = MagicMock()
    fake_backend.create_volume.return_value = VolumeInfo(volume_id="/pools/local/disk1", size_bytes=1024, format="qcow2")
    monkeypatch.setattr(disk_ops, "get_backend", lambda storage_type, path: fake_backend)

    downloaded_path = _fake_downloaded_file()
    monkeypatch.setattr(image_fetch, "download_image", lambda config, image_uuid, expected_sha256="": downloaded_path)

    def failing_run(args, **kwargs):
        raise StorageOperationError("qemu-img convert failed")

    monkeypatch.setattr(disk_ops, "run", failing_run)

    with pytest.raises(StorageOperationError):
        disk_ops.create_disk({"storage_type": "DIRECTORY", "storage_path": "/pools/local", "disk_uuid": "disk1", "size_bytes": 1024, "image_uuid": "img-1"}, config=_FakeConfig())

    assert not os.path.exists(downloaded_path)
