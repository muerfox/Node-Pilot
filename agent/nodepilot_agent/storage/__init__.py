from nodepilot_agent.storage.base import PoolInfo, StorageBackend, StorageOperationError, VolumeInfo
from nodepilot_agent.storage.directory import DirectoryBackend
from nodepilot_agent.storage.lvm import LVMBackend
from nodepilot_agent.storage.lvm_thin import LVMThinBackend
from nodepilot_agent.storage.nfs import NFSBackend
from nodepilot_agent.storage.zfs import ZFSBackend

_BACKENDS: dict[str, type[StorageBackend]] = {
    "DIRECTORY": DirectoryBackend,
    "NFS": NFSBackend,
    "LVM": LVMBackend,
    "LVM_THIN": LVMThinBackend,
    "ZFS": ZFSBackend,
}


def get_backend(storage_type: str, pool_path: str) -> StorageBackend:
    try:
        backend_cls = _BACKENDS[storage_type.upper()]
    except KeyError as exc:
        raise StorageOperationError(f"Unsupported storage type: {storage_type!r}") from exc
    return backend_cls(pool_path)


__all__ = ["get_backend", "StorageBackend", "StorageOperationError", "VolumeInfo", "PoolInfo"]
