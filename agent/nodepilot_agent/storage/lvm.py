"""Plain (thick) LVM storage: one logical volume per NodePilot volume,
raw block device -- no built-in snapshot support exposed here (LVM does
support snapshots, but a plain thick-LV snapshot needs pre-allocated COW
space sized by the caller, which this pool type doesn't model; use
LVM-thin for snapshot-capable pools)."""
from __future__ import annotations

import re

from nodepilot_agent.storage.base import PoolInfo, StorageBackend, StorageOperationError, VolumeInfo, run

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_name(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise StorageOperationError(f"Unsafe volume name: {name!r}")
    return name


class LVMBackend(StorageBackend):
    """`pool_path` is the volume group name, e.g. "vg-data"."""

    def create_volume(self, name: str, size_bytes: int, *, format: str = "raw") -> VolumeInfo:
        name = _validate_name(name)
        run(["lvcreate", "-y", "-L", f"{size_bytes}B", "-n", name, self.pool_path])
        return VolumeInfo(volume_id=f"{self.pool_path}/{name}", size_bytes=size_bytes, format="raw")

    def delete_volume(self, volume_id: str) -> None:
        run(["lvremove", "-f", volume_id])

    def resize_volume(self, volume_id: str, new_size_bytes: int) -> None:
        run(["lvextend", "-L", f"{new_size_bytes}B", volume_id])

    def clone_volume(self, source_volume_id: str, new_name: str, *, linked: bool = False) -> VolumeInfo:
        if linked:
            raise NotImplementedError("Linked clones are not supported on plain LVM; use an LVM-thin pool.")
        new_name = _validate_name(new_name)
        size = self._lv_size_bytes(source_volume_id)
        dest = f"{self.pool_path}/{new_name}"
        run(["lvcreate", "-y", "-L", f"{size}B", "-n", new_name, self.pool_path])
        run(["dd", f"if={source_volume_id}", f"of={dest}", "bs=4M", "conv=fsync"])
        return VolumeInfo(volume_id=dest, size_bytes=size, format="raw")

    def pool_info(self) -> PoolInfo:
        result = run(["vgs", "--noheadings", "--units", "b", "--nosuffix", "-o", "vg_size,vg_free", self.pool_path])
        total_str, free_str = result.stdout.split()
        total, free = int(total_str), int(free_str)
        return PoolInfo(capacity_bytes=total, used_bytes=total - free, available_bytes=free)

    @staticmethod
    def _lv_size_bytes(volume_id: str) -> int:
        result = run(["lvs", "--noheadings", "--units", "b", "--nosuffix", "-o", "lv_size", volume_id])
        return int(result.stdout.strip())
