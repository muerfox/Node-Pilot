"""
Regression test for a cross-tenant IDOR: HasResourcePermission.
has_object_permission used to fall back to a client-supplied
`?organization=` query parameter whenever the target object had no
*direct* `organization` field (true of StoragePool, Network, Subnet,
IPAddress, IPPool, Snapshot, Backup, ...). That let a user who is merely
a Member of org A -- with no write permission there -- act on an org-A
object by passing `?organization=<org-B-uuid>` for an unrelated org B
where they *do* hold the permission, "borrowing" that grant across
tenants. See apps.common.permissions.HasResourcePermission.
_resolve_organization_from_object, which now derives the organization
strictly from the object itself.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.nodes.models import Node
from apps.organizations.models import Membership, Organization
from apps.storage.models import StoragePool

pytestmark = pytest.mark.django_db


@pytest.fixture
def org_b(db):
    return Organization.objects.create(name="Org B", slug="org-b")


@pytest.fixture
def node_b(org_b):
    return Node.objects.create(organization=org_b, name="node-b", hostname="node-b.local")


@pytest.fixture
def pool_in_org_a(node):
    """`node` (from conftest.py) belongs to the `organization` fixture -- call it Org A."""
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def attacker(user, organization, org_b, grant_permission):
    """A user who is a plain Member of Org A (no permission grants there)
    but holds storage.manage in the unrelated Org B."""
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, org_b, "storage.manage")
    return user


def test_cannot_delete_a_storage_pool_by_borrowing_a_permission_from_another_org(attacker, pool_in_org_a, org_b):
    client = APIClient()
    client.force_authenticate(user=attacker)

    response = client.delete(f"/api/v1/storages/{pool_in_org_a.uuid}/?organization={org_b.uuid}")

    assert response.status_code == 403
    assert StoragePool.objects.filter(pk=pool_in_org_a.pk).exists()


def test_cannot_update_a_storage_pool_by_borrowing_a_permission_from_another_org(attacker, pool_in_org_a, org_b):
    client = APIClient()
    client.force_authenticate(user=attacker)

    response = client.patch(f"/api/v1/storages/{pool_in_org_a.uuid}/?organization={org_b.uuid}", {"enabled": False}, format="json")

    assert response.status_code == 403
    pool_in_org_a.refresh_from_db()
    assert pool_in_org_a.enabled is True


def test_org_admin_can_still_manage_their_own_pool(user, organization, node, grant_permission, pool_in_org_a):
    """Sanity check the fix didn't also break the legitimate path."""
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "storage.manage")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.patch(f"/api/v1/storages/{pool_in_org_a.uuid}/", {"enabled": False}, format="json")

    assert response.status_code == 200
    pool_in_org_a.refresh_from_db()
    assert pool_in_org_a.enabled is False
