"""Filesystem-directory-backed storage (qcow2/raw files via qemu-img).
Also used, as-is, for NFS pools once the export is mounted at pool_path --
see nfs.py."""
from __future__ import annotations

import os
import re
import shutil

from nodepilot_agent.storage.base import PoolInfo, StorageBackend, StorageOperationError, VolumeInfo, run

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_name(name: str) -> str:
    """Volume names come from the controller but end up as filesystem
    path components -- reject anything that isn't a plain safe token so a
    malicious/buggy payload can never traverse outside the pool
    (section 46: path traversal protection)."""
    if not _SAFE_NAME.match(name):
        raise StorageOperationError(f"Unsafe volume name: {name!r}")
    return name


class DirectoryBackend(StorageBackend):
    def _path_for(self, name: str) -> str:
        return os.path.join(self.pool_path, _validate_name(name))

    def create_volume(self, name: str, size_bytes: int, *, format: str = "qcow2") -> VolumeInfo:
        path = self._path_for(name)
        run(["qemu-img", "create", "-f", format, path, str(size_bytes)])
        return VolumeInfo(volume_id=path, size_bytes=size_bytes, format=format)

    def delete_volume(self, volume_id: str) -> None:
        self._assert_within_pool(volume_id)
        if os.path.exists(volume_id):
            os.remove(volume_id)

    def resize_volume(self, volume_id: str, new_size_bytes: int) -> None:
        self._assert_within_pool(volume_id)
        run(["qemu-img", "resize", volume_id, str(new_size_bytes)])

    def clone_volume(self, source_volume_id: str, new_name: str, *, linked: bool = False) -> VolumeInfo:
        self._assert_within_pool(source_volume_id)
        dest = self._path_for(new_name)
        info = run(["qemu-img", "info", "--output=json", source_volume_id])
        fmt = "qcow2" if '"format": "qcow2"' in info.stdout else "raw"

        if linked and fmt == "qcow2":
            run(["qemu-img", "create", "-f", "qcow2", "-b", source_volume_id, "-F", "qcow2", dest])
        else:
            run(["qemu-img", "convert", "-O", fmt, source_volume_id, dest])

        size = os.path.getsize(dest) if not linked else _qcow2_virtual_size(dest)
        return VolumeInfo(volume_id=dest, size_bytes=size, format=fmt)

    def pool_info(self) -> PoolInfo:
        usage = shutil.disk_usage(self.pool_path)
        return PoolInfo(capacity_bytes=usage.total, used_bytes=usage.used, available_bytes=usage.free)

    def _assert_within_pool(self, volume_id: str) -> None:
        real_pool = os.path.realpath(self.pool_path)
        real_volume = os.path.realpath(volume_id)
        if os.path.commonpath([real_pool, real_volume]) != real_pool:
            raise StorageOperationError(f"Refusing to operate outside the storage pool: {volume_id!r}")


def _qcow2_virtual_size(path: str) -> int:
    import json

    info = run(["qemu-img", "info", "--output=json", path])
    return json.loads(info.stdout).get("virtual-size", 0)
