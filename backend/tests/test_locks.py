from apps.common.locks import LockAcquisitionError, RedisLock, try_lock


def test_acquire_and_release():
    lock = RedisLock("test:1", ttl_seconds=5)
    assert lock.acquire(blocking=False) is True
    assert lock.release() is True


def test_second_acquire_fails_while_held():
    first = RedisLock("test:2", ttl_seconds=5)
    second = RedisLock("test:2", ttl_seconds=5)
    assert first.acquire(blocking=False) is True
    assert second.acquire(blocking=False) is False
    first.release()
    assert second.acquire(blocking=False) is True


def test_release_only_by_owner_token():
    first = RedisLock("test:3", ttl_seconds=5)
    first.acquire(blocking=False)
    # A different RedisLock instance for the same key (different token)
    # must not be able to release someone else's lock.
    impostor = RedisLock("test:3", ttl_seconds=5)
    assert impostor.release() is False
    assert first.release() is True


def test_context_manager_releases_on_exit():
    with RedisLock("test:4", ttl_seconds=5) as lock:
        assert lock.token
    # After the context exits, a new lock on the same key should succeed.
    assert RedisLock("test:4", ttl_seconds=5).acquire(blocking=False) is True


def test_try_lock_raises_when_busy():
    holder = RedisLock("test:5", ttl_seconds=5)
    holder.acquire(blocking=False)
    try:
        raised = False
        try:
            with try_lock("test:5"):
                pass
        except LockAcquisitionError:
            raised = True
        assert raised is True
    finally:
        holder.release()
