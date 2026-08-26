"""LVM-thin storage: thin-provisioned volumes with real snapshot support
via lvcreate -s."""
from __future__ import annotations

import re

from nodepilot_agent.storage.base import PoolInfo, StorageBackend, StorageOperationError, VolumeInfo, run

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_name(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise StorageOperationError(f"Unsafe volume name: {name!r}")
    return name


class LVMThinBackend(StorageBackend):
    """`pool_path` is "vg-name/thinpool-name"."""

    def __init__(self, pool_path: str):
        super().__init__(pool_path)
        self.vg, _, self.thinpool = pool_path.partition("/")
        if not self.thinpool:
            raise StorageOperationError(f"LVM-thin pool_path must be 'vg/thinpool', got {pool_path!r}")

    def create_volume(self, name: str, size_bytes: int, *, format: str = "raw") -> VolumeInfo:
        name = _validate_name(name)
        run(["lvcreate", "-y", "-T", f"{self.vg}/{self.thinpool}", "-V", f"{size_bytes}B", "-n", name])
        return VolumeInfo(volume_id=f"{self.vg}/{name}", size_bytes=size_bytes, format="raw")

    def delete_volume(self, volume_id: str) -> None:
        run(["lvremove", "-f", volume_id])

    def resize_volume(self, volume_id: str, new_size_bytes: int) -> None:
        run(["lvextend", "-L", f"{new_size_bytes}B", volume_id])

    def clone_volume(self, source_volume_id: str, new_name: str, *, linked: bool = False) -> VolumeInfo:
        new_name = _validate_name(new_name)
        dest = f"{self.vg}/{new_name}"
        if linked:
            # A thin snapshot *is* a cheap linked clone.
            run(["lvcreate", "-y", "-s", "-n", new_name, source_volume_id])
        else:
            size = self._lv_size_bytes(source_volume_id)
            run(["lvcreate", "-y", "-T", f"{self.vg}/{self.thinpool}", "-V", f"{size}B", "-n", new_name])
            run(["dd", f"if={source_volume_id}", f"of={dest}", "bs=4M", "conv=fsync"])
        return VolumeInfo(volume_id=dest, size_bytes=self._lv_size_bytes(dest), format="raw")

    def create_snapshot(self, volume_id: str, snapshot_name: str) -> str:
        snapshot_name = _validate_name(snapshot_name)
        run(["lvcreate", "-y", "-s", "-n", f"{snapshot_name}", volume_id])
        return f"{self.vg}/{snapshot_name}"

    def delete_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        run(["lvremove", "-f", f"{self.vg}/{snapshot_name}"])

    def rollback_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        run(["lvconvert", "--merge", f"{self.vg}/{snapshot_name}"])

    def pool_info(self) -> PoolInfo:
        result = run(["lvs", "--noheadings", "--units", "b", "--nosuffix", "-o", "lv_size,data_percent", f"{self.vg}/{self.thinpool}"])
        size_str, used_pct_str = result.stdout.split()
        total = int(size_str)
        used = int(total * (float(used_pct_str) / 100))
        return PoolInfo(capacity_bytes=total, used_bytes=used, available_bytes=total - used)

    @staticmethod
    def _lv_size_bytes(volume_id: str) -> int:
        result = run(["lvs", "--noheadings", "--units", "b", "--nosuffix", "-o", "lv_size", volume_id])
        return int(result.stdout.strip())
