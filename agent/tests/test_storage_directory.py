import shutil

import pytest

from nodepilot_agent.storage.base import StorageOperationError
from nodepilot_agent.storage.directory import DirectoryBackend

requires_qemu_img = pytest.mark.skipif(shutil.which("qemu-img") is None, reason="qemu-img not installed in this environment")


def test_rejects_unsafe_volume_names(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    with pytest.raises(StorageOperationError):
        backend.create_volume("../../etc/passwd", 1024)


def test_rejects_path_traversal_in_delete(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    outside = tmp_path.parent / "outside-file"
    outside.write_text("do not delete me")
    with pytest.raises(StorageOperationError):
        backend.delete_volume(str(outside))
    assert outside.exists()


@requires_qemu_img
def test_create_and_delete_volume(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    info = backend.create_volume("disk-1", 64 * 1024 * 1024, format="qcow2")
    assert (tmp_path / "disk-1").exists()
    assert info.format == "qcow2"

    backend.delete_volume(info.volume_id)
    assert not (tmp_path / "disk-1").exists()


@requires_qemu_img
def test_resize_volume(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    info = backend.create_volume("disk-2", 64 * 1024 * 1024, format="qcow2")
    backend.resize_volume(info.volume_id, 128 * 1024 * 1024)  # should not raise


@requires_qemu_img
def test_clone_volume_full(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    info = backend.create_volume("disk-3", 64 * 1024 * 1024, format="qcow2")
    clone = backend.clone_volume(info.volume_id, "disk-3-clone", linked=False)
    assert (tmp_path / "disk-3-clone").exists()


def test_pool_info_reports_real_disk_usage(tmp_path):
    backend = DirectoryBackend(str(tmp_path))
    info = backend.pool_info()
    assert info.capacity_bytes > 0
    assert info.available_bytes >= 0
