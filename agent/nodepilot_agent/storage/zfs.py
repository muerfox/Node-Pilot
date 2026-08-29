"""ZFS-backed storage: zvols (block devices) with native snapshot/clone
support."""
from __future__ import annotations

import re

from nodepilot_agent.storage.base import PoolInfo, StorageBackend, StorageOperationError, VolumeInfo, run

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_name(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise StorageOperationError(f"Unsafe volume name: {name!r}")
    return name


class ZFSBackend(StorageBackend):
    """`pool_path` is the ZFS dataset prefix volumes are created under,
    e.g. "tank/nodepilot"."""

    def _assert_within_pool(self, dataset: str) -> None:
        """
        Mirrors DirectoryBackend._assert_within_pool -- the agent's own
        last line of defense against a `volume_id` outside this pool's
        dataset tree (see LVMBackend._assert_within_vg for the full
        rationale). Matters even more here than for LVM: `zfs destroy` is
        called with `-r` (recursive), so an unscoped call against
        `self.pool_path` itself -- not just some unrelated dataset --
        would destroy this entire pool's dataset tree in one shot.
        """
        prefix = f"{self.pool_path}/"
        if dataset == self.pool_path or not dataset.startswith(prefix):
            raise StorageOperationError(f"Refusing to operate on a dataset outside this pool: {dataset!r}")

    def create_volume(self, name: str, size_bytes: int, *, format: str = "raw") -> VolumeInfo:
        name = _validate_name(name)
        dataset = f"{self.pool_path}/{name}"
        run(["zfs", "create", "-V", f"{size_bytes}B", "-s", dataset])
        return VolumeInfo(volume_id=dataset, size_bytes=size_bytes, format="raw")

    def delete_volume(self, volume_id: str) -> None:
        self._assert_within_pool(volume_id)
        run(["zfs", "destroy", "-r", volume_id])

    def resize_volume(self, volume_id: str, new_size_bytes: int) -> None:
        self._assert_within_pool(volume_id)
        run(["zfs", "set", f"volsize={new_size_bytes}", volume_id])

    def clone_volume(self, source_volume_id: str, new_name: str, *, linked: bool = False) -> VolumeInfo:
        new_name = _validate_name(new_name)
        dest = f"{self.pool_path}/{new_name}"
        if linked:
            snap = f"{source_volume_id}@clone-base-{new_name}"
            run(["zfs", "snapshot", snap])
            run(["zfs", "clone", snap, dest])
        else:
            _pipe_send_receive(source_volume_id, dest)
        size = self._volsize_bytes(dest)
        return VolumeInfo(volume_id=dest, size_bytes=size, format="raw")

    def create_snapshot(self, volume_id: str, snapshot_name: str) -> str:
        snapshot_name = _validate_name(snapshot_name)
        snap = f"{volume_id}@{snapshot_name}"
        run(["zfs", "snapshot", snap])
        return snap

    def delete_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        run(["zfs", "destroy", f"{volume_id}@{snapshot_name}"])

    def rollback_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        run(["zfs", "rollback", "-r", f"{volume_id}@{snapshot_name}"])

    def pool_info(self) -> PoolInfo:
        result = run(["zfs", "list", "-H", "-p", "-o", "avail,used", self.pool_path])
        avail_str, used_str = result.stdout.split()
        avail, used = int(avail_str), int(used_str)
        return PoolInfo(capacity_bytes=avail + used, used_bytes=used, available_bytes=avail)

    @staticmethod
    def _volsize_bytes(dataset: str) -> int:
        result = run(["zfs", "get", "-H", "-p", "-o", "value", "volsize", dataset])
        return int(result.stdout.strip())


def _pipe_send_receive(source_dataset: str, dest_dataset: str) -> None:
    """A full (non-linked) ZFS clone is send | receive of a throwaway
    snapshot -- argv lists on both ends of the pipe, no shell involved."""
    import subprocess

    from nodepilot_agent.storage.base import StorageOperationError

    snap = f"{source_dataset}@full-clone-tmp"
    run(["zfs", "snapshot", snap])
    try:
        send_proc = subprocess.Popen(["zfs", "send", snap], stdout=subprocess.PIPE)
        recv_proc = subprocess.run(["zfs", "receive", dest_dataset], stdin=send_proc.stdout, capture_output=True, text=True)
        send_proc.stdout.close()
        send_proc.wait()
        if recv_proc.returncode != 0:
            raise StorageOperationError(f"zfs receive failed: {recv_proc.stderr}")
    finally:
        run(["zfs", "destroy", snap], check=False)
