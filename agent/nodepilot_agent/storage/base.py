"""
Storage backend abstraction. Every backend implements the same interface
so operation handlers never special-case a storage type -- callers ask
the pool's capability set (mirrors backend/apps/storage StorageType
choices) instead of hardcoding "if type == X" outside this package.

Section 46: every subprocess invocation here uses an argument list, never
`shell=True` with interpolated strings -- so a crafted volume name or
path component cannot inject shell syntax.
"""
from __future__ import annotations

import abc
import dataclasses
import subprocess


class StorageOperationError(RuntimeError):
    pass


def run(args: list[str], *, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    """The one place subprocess is invoked for storage operations --
    always argv-list form, never a shell string."""
    try:
        return subprocess.run(args, check=check, timeout=timeout, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise StorageOperationError(f"{' '.join(args)} failed (exit {exc.returncode}): {exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise StorageOperationError(f"{' '.join(args)} timed out after {timeout}s") from exc


@dataclasses.dataclass
class VolumeInfo:
    volume_id: str  # backend-specific: filesystem path, or vg/lv, or pool/dataset
    size_bytes: int
    format: str


@dataclasses.dataclass
class PoolInfo:
    capacity_bytes: int
    used_bytes: int
    available_bytes: int


class StorageBackend(abc.ABC):
    def __init__(self, pool_path: str):
        self.pool_path = pool_path

    @abc.abstractmethod
    def create_volume(self, name: str, size_bytes: int, *, format: str = "qcow2") -> VolumeInfo: ...

    @abc.abstractmethod
    def delete_volume(self, volume_id: str) -> None: ...

    @abc.abstractmethod
    def resize_volume(self, volume_id: str, new_size_bytes: int) -> None: ...

    @abc.abstractmethod
    def clone_volume(self, source_volume_id: str, new_name: str, *, linked: bool = False) -> VolumeInfo: ...

    @abc.abstractmethod
    def pool_info(self) -> PoolInfo: ...

    # Snapshots are optional -- not every backend supports them (section
    # 24/14: "advertise capabilities rather than relying on hardcoded
    # assumptions"). The default raises; capable backends override.
    def create_snapshot(self, volume_id: str, snapshot_name: str) -> str:
        raise NotImplementedError(f"{type(self).__name__} does not support snapshots")

    def delete_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not support snapshots")

    def rollback_snapshot(self, volume_id: str, snapshot_name: str) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not support snapshots")
