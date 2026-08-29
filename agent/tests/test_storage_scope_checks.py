"""
The block-storage backends (LVM/LVM-thin/ZFS) must refuse to
delete/resize a volume_id outside the pool they were constructed for --
the same guarantee DirectoryBackend already provides via
_assert_within_pool (see test_storage_directory.py). The scope check
runs before any subprocess call, so these tests don't need lvm2/zfsutils
installed -- StorageOperationError is raised before `run()` is reached.
"""
import pytest

from nodepilot_agent.storage.base import StorageOperationError
from nodepilot_agent.storage.lvm import LVMBackend
from nodepilot_agent.storage.lvm_thin import LVMThinBackend
from nodepilot_agent.storage.zfs import ZFSBackend


def test_lvm_refuses_to_delete_a_volume_in_a_different_vg():
    backend = LVMBackend("vg-data")
    with pytest.raises(StorageOperationError):
        backend.delete_volume("vg-other/some-lv")


def test_lvm_refuses_to_resize_a_volume_in_a_different_vg():
    backend = LVMBackend("vg-data")
    with pytest.raises(StorageOperationError):
        backend.resize_volume("vg-other/some-lv", 10 * 1024**3)


def test_lvm_thin_refuses_to_delete_a_volume_in_a_different_vg():
    backend = LVMThinBackend("vg-data/thinpool")
    with pytest.raises(StorageOperationError):
        backend.delete_volume("vg-other/some-lv")


def test_zfs_refuses_to_destroy_a_dataset_outside_the_pool():
    backend = ZFSBackend("tank/nodepilot")
    with pytest.raises(StorageOperationError):
        backend.delete_volume("tank/other-app/some-volume")


def test_zfs_refuses_to_destroy_the_pool_dataset_itself():
    """`zfs destroy -r` is recursive -- a volume_id equal to the pool's
    own dataset must never reach it, or an entire pool tree could be
    wiped in one call."""
    backend = ZFSBackend("tank/nodepilot")
    with pytest.raises(StorageOperationError):
        backend.delete_volume("tank/nodepilot")


def test_zfs_refuses_to_resize_a_dataset_outside_the_pool():
    backend = ZFSBackend("tank/nodepilot")
    with pytest.raises(StorageOperationError):
        backend.resize_volume("tank/other-app/some-volume", 10 * 1024**3)
