"""
Distributed locking for operations that must never run concurrently, e.g.:

    vm:{uuid}:lifecycle
    vm:{uuid}:storage
    node:{id}:migration
    storage:{id}:allocation

Locks are Redis SET NX PX with an ownership token so a lock can only be
released by the holder that acquired it (avoids releasing a lock that has
since been acquired by someone else after our TTL expired).
"""
from __future__ import annotations

import contextlib
import time
import uuid

from apps.common.redis_client import get_redis

_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_EXTEND_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class LockAcquisitionError(Exception):
    """Raised when a distributed lock cannot be acquired within the timeout."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Could not acquire lock for {key!r}: resource is busy")


class RedisLock:
    """
    Usage:

        with RedisLock(f"vm:{vm.uuid}:lifecycle", timeout=30):
            ...

    Or manually:

        lock = RedisLock("node:1:migration")
        if not lock.acquire(blocking=False):
            raise LockAcquisitionError(lock.key)
        try:
            ...
        finally:
            lock.release()
    """

    def __init__(self, key: str, ttl_seconds: int = 60, namespace: str = "nodepilot:lock"):
        self.key = f"{namespace}:{key}"
        self.ttl_seconds = ttl_seconds
        self.token = uuid.uuid4().hex
        self._client = get_redis()

    def acquire(self, blocking: bool = True, timeout: float = 10.0, retry_interval: float = 0.1) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            acquired = self._client.set(self.key, self.token, nx=True, px=int(self.ttl_seconds * 1000))
            if acquired:
                return True
            if not blocking or time.monotonic() >= deadline:
                return False
            time.sleep(retry_interval)

    def extend(self, additional_ttl_seconds: int | None = None) -> bool:
        ttl_ms = int((additional_ttl_seconds or self.ttl_seconds) * 1000)
        result = self._client.eval(_EXTEND_SCRIPT, 1, self.key, self.token, ttl_ms)
        return bool(result)

    def release(self) -> bool:
        result = self._client.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        return bool(result)

    def __enter__(self) -> "RedisLock":
        if not self.acquire(blocking=True, timeout=10.0):
            raise LockAcquisitionError(self.key)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


@contextlib.contextmanager
def try_lock(key: str, ttl_seconds: int = 60):
    """Non-blocking variant: raises LockAcquisitionError immediately if busy."""
    lock = RedisLock(key, ttl_seconds=ttl_seconds)
    if not lock.acquire(blocking=False):
        raise LockAcquisitionError(lock.key)
    try:
        yield lock
    finally:
        lock.release()
