from apps.common.locks import RedisLock


def lifecycle_lock(vm, ttl_seconds: int = 120) -> RedisLock:
    """Guards start/stop/reboot/delete/migrate -- section 20's
    "vm:{uuid}:lifecycle" -- so e.g. start+delete can never race."""
    return RedisLock(f"vm:{vm.uuid}:lifecycle", ttl_seconds=ttl_seconds)


def storage_lock(vm, ttl_seconds: int = 300) -> RedisLock:
    """Guards disk resize/attach/detach and snapshot create/delete/rollback
    -- section 20's "vm:{uuid}:storage"."""
    return RedisLock(f"vm:{vm.uuid}:storage", ttl_seconds=ttl_seconds)
