"""
StoragePoolViewSet used to be a plain ModelViewSet with no perform_create
override -- registering a pool was a database-only operation.
CREATE_STORAGE_POOL and GET_STORAGE_POOL_INFO are fully implemented on
the agent (nodepilot_agent.operations.storage_ops), but nothing on the
controller ever dispatched either one, so capacity_bytes/used_bytes/
available_bytes -- read-only fields implying they're system-reported --
sat at 0 forever, and a DIRECTORY pool's path was never actually created
on the host.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.jobs.models import JobStatus
from apps.organizations.models import Membership
from apps.storage.models import StoragePool, StoragePoolStatus

pytestmark = pytest.mark.django_db


def _fake_agent(monkeypatch, *, fail=False, info=None):
    import apps.nodes.agent_client as agent_client_module

    calls = []
    info = info or {"capacity_bytes": 1_000_000_000, "used_bytes": 200_000_000, "available_bytes": 800_000_000}

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append((operation.value, payload))
        if fail:
            raise RuntimeError("agent unreachable")
        if operation.value == "GET_STORAGE_POOL_INFO":
            return dict(info)
        return {}

    monkeypatch.setattr(agent_client_module, "send_operation", fake_send_operation)
    return calls


# --- service + task: create ------------------------------------------------


def test_creating_a_directory_pool_creates_the_path_then_fetches_real_capacity(node, user, monkeypatch):
    from apps.storage import services, tasks

    calls = _fake_agent(monkeypatch)
    pool, job = services.create_storage_pool(node=node, name="local", type="DIRECTORY", path="/var/lib/nodepilot/pools/local", shared=False, enabled=True, capabilities=None, requested_by=user)
    assert pool.status == StoragePoolStatus.OFFLINE  # not yet confirmed
    assert pool.capacity_bytes == 0

    tasks.create_storage_pool_task(job.pk, pool.pk)

    pool.refresh_from_db()
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert pool.status == StoragePoolStatus.ONLINE
    assert pool.capacity_bytes == 1_000_000_000
    assert pool.used_bytes == 200_000_000
    assert pool.available_bytes == 800_000_000
    assert [c[0] for c in calls] == ["CREATE_STORAGE_POOL", "GET_STORAGE_POOL_INFO"]


def test_creating_a_non_directory_pool_only_registers_the_existing_pool(node, user, monkeypatch):
    """LVM/ZFS/NFS/Ceph-RBD pools are provisioned out-of-band on the host
    (agent storage_ops.create_storage_pool intentionally refuses to create
    them) -- NodePilot should only fetch info to register what's already
    there, never attempt CREATE_STORAGE_POOL for these types."""
    from apps.storage import services, tasks

    calls = _fake_agent(monkeypatch)
    pool, job = services.create_storage_pool(node=node, name="vg0", type="LVM", path="vg0", shared=False, enabled=True, capabilities=None, requested_by=user)

    tasks.create_storage_pool_task(job.pk, pool.pk)

    pool.refresh_from_db()
    assert pool.status == StoragePoolStatus.ONLINE
    assert [c[0] for c in calls] == ["GET_STORAGE_POOL_INFO"]


def test_create_storage_pool_task_marks_error_on_agent_failure(node, user, monkeypatch):
    from apps.storage import services, tasks

    _fake_agent(monkeypatch, fail=True)
    pool, job = services.create_storage_pool(node=node, name="local", type="DIRECTORY", path="/data", shared=False, enabled=True, capabilities=None, requested_by=user)

    with pytest.raises(RuntimeError):
        tasks.create_storage_pool_task(job.pk, pool.pk)

    pool.refresh_from_db()
    job.refresh_from_db()
    assert pool.status == StoragePoolStatus.ERROR
    assert job.status == JobStatus.FAILED
    assert StoragePool.objects.filter(pk=pool.pk).exists()  # row is kept, not silently dropped


# --- periodic refresh --------------------------------------------------


def test_refresh_storage_pools_task_updates_capacity_for_online_nodes(node, monkeypatch):
    from apps.storage.tasks import refresh_storage_pools_task

    calls = _fake_agent(monkeypatch, info={"capacity_bytes": 42, "used_bytes": 1, "available_bytes": 41})
    from django.utils import timezone

    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])
    pool = StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/data", enabled=True, status=StoragePoolStatus.ONLINE)

    refreshed = refresh_storage_pools_task()

    assert refreshed == 1
    pool.refresh_from_db()
    assert pool.capacity_bytes == 42
    assert calls == [("GET_STORAGE_POOL_INFO", {"storage_type": "DIRECTORY", "storage_path": "/data"})]


def test_refresh_storage_pools_task_skips_disabled_pools(node, monkeypatch):
    from apps.storage.tasks import refresh_storage_pools_task

    calls = _fake_agent(monkeypatch)
    from django.utils import timezone

    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])
    StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/data", enabled=False, status=StoragePoolStatus.ONLINE)

    assert refresh_storage_pools_task() == 0
    assert calls == []


def test_refresh_storage_pools_task_skips_pools_on_offline_nodes(node, monkeypatch):
    from apps.storage.tasks import refresh_storage_pools_task

    calls = _fake_agent(monkeypatch)
    node.last_seen = None  # never seen -- effective_status() is OFFLINE
    node.save(update_fields=["last_seen"])
    StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/data", enabled=True, status=StoragePoolStatus.ONLINE)

    assert refresh_storage_pools_task() == 0
    assert calls == []


def test_refresh_storage_pools_task_marks_a_pool_error_without_stopping_the_sweep(node, monkeypatch):
    from apps.storage.tasks import refresh_storage_pools_task
    from django.utils import timezone

    _fake_agent(monkeypatch, fail=True)
    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])
    pool = StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/data", enabled=True, status=StoragePoolStatus.ONLINE)

    assert refresh_storage_pools_task() == 0  # failed, not counted as refreshed
    pool.refresh_from_db()
    assert pool.status == StoragePoolStatus.ERROR


# --- API-level ------------------------------------------------------------


def test_creating_a_storage_pool_through_the_api_dispatches_a_job(user, organization, node, grant_permission, monkeypatch):
    _fake_agent(monkeypatch)
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "storage.manage")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post("/api/v1/storages/", {"node": str(node.uuid), "name": "local", "type": "DIRECTORY", "path": "/data"}, format="json")

    assert response.status_code == 201
    assert response.data["status"] == StoragePoolStatus.OFFLINE
    assert response.data["capacity_bytes"] == 0
