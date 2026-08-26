"""
Shared fixtures. Redis is faked (fakeredis) so the suite never depends on
a live Redis instance -- every consumer of apps.common.redis_client.get_redis
transitively gets the fake client because we patch the underlying
redis.Redis.from_url rather than the many separate `from ... import
get_redis` bindings scattered across modules.
"""
from __future__ import annotations

import fakeredis
import pytest
import redis


@pytest.fixture(autouse=True)
def clear_django_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    from apps.common import redis_client

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: fake))
    redis_client.get_redis.cache_clear()
    fake.flushall()
    yield fake
    redis_client.get_redis.cache_clear()


@pytest.fixture
def organization(db):
    from apps.organizations.models import Organization

    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def project(organization):
    from apps.organizations.models import Project

    return Project.objects.create(organization=organization, name="Production", slug="production")


@pytest.fixture
def user(db):
    from apps.users.models import User

    return User.objects.create_user(username="alice", email="alice@example.com", password="correct-horse-battery-staple")


@pytest.fixture
def superuser(db):
    from apps.users.models import User

    return User.objects.create_superuser(username="root", email="root@example.com", password="correct-horse-battery-staple")


@pytest.fixture
def grant_permission(db):
    """grant_permission(user, organization, "vm.create") -- creates the
    Role/Permission/RoleAssignment chain needed for that grant to take
    effect."""
    from apps.permissions.models import Permission, Role, RoleAssignment

    def _grant(target_user, organization, *codenames):
        role = Role.objects.create(name=f"test-role-{organization.pk}-{'-'.join(codenames)}", organization=organization)
        for codename in codenames:
            permission, _ = Permission.objects.get_or_create(codename=codename, defaults={"description": codename})
            role.permissions.add(permission)
        RoleAssignment.objects.create(user=target_user, organization=organization, role=role)
        return role

    return _grant


@pytest.fixture
def node(organization):
    from apps.nodes.models import Node

    return Node.objects.create(organization=organization, name="node-01", hostname="node-01.local")
