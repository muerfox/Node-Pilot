"""
APIToken.scopes ("List of permission codenames this token is limited to,
or [] for the user's full permission set") was fully user-settable at
token creation -- validated against the real permission catalog -- but
was never actually enforced anywhere. A user who created a token scoped
to e.g. ["node.view"], believing it limited to read-only node access for
some third-party integration, actually handed out a token carrying their
full permission set, since HasResourcePermission only ever checked the
user's own role-based permissions and never consulted the authenticating
token's scope at all. See apps.common.permissions.HasResourcePermission
._token_permits.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.authentication.models import APIToken
from apps.nodes.models import Node
from apps.organizations.models import Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def full_access_user(user, organization, grant_permission):
    """A user who genuinely holds both node.view and node.manage in their
    organization -- so any denial below is provably about the token's
    scope, not the user lacking the underlying permission."""
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "node.view", "node.manage")
    return user


def _client_with_token(user, *, scopes: list[str]) -> APIClient:
    raw_token, token_hash, prefix = APIToken.generate()
    APIToken.objects.create(user=user, name="test-token", token_hash=token_hash, prefix=prefix, scopes=scopes)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {raw_token}")
    return client


def test_a_token_scoped_to_view_can_list_nodes(full_access_user, node):
    client = _client_with_token(full_access_user, scopes=["node.view"])
    response = client.get("/api/v1/nodes/")
    assert response.status_code == 200


def test_the_same_view_scoped_token_cannot_create_a_node(full_access_user, organization):
    """The real regression: the user themselves can create nodes
    (node.manage granted above), but this token was only ever scoped to
    node.view and must not silently inherit the user's full access."""
    client = _client_with_token(full_access_user, scopes=["node.view"])
    response = client.post("/api/v1/nodes/", {"organization": str(organization.uuid), "name": "sneaky", "hostname": "sneaky.local"}, format="json")
    assert response.status_code == 403
    assert not Node.objects.filter(name="sneaky").exists()


def test_a_view_scoped_token_cannot_delete_a_node_either(full_access_user, node):
    client = _client_with_token(full_access_user, scopes=["node.view"])
    response = client.delete(f"/api/v1/nodes/{node.uuid}/")
    assert response.status_code == 403
    assert Node.objects.filter(pk=node.pk).exists()


def test_an_unscoped_token_carries_the_users_full_permission_set(full_access_user, organization):
    """Empty scopes ([]) is documented as "the user's full permission
    set" -- must remain fully backward compatible with tokens created
    before this fix, and with the documented default."""
    client = _client_with_token(full_access_user, scopes=[])
    response = client.post("/api/v1/nodes/", {"organization": str(organization.uuid), "name": "allowed", "hostname": "allowed.local"}, format="json")
    assert response.status_code == 201


def test_a_correctly_scoped_token_can_do_what_it_was_scoped_for(full_access_user, organization):
    client = _client_with_token(full_access_user, scopes=["node.view", "node.manage"])
    response = client.post("/api/v1/nodes/", {"organization": str(organization.uuid), "name": "allowed", "hostname": "allowed.local"}, format="json")
    assert response.status_code == 201


def test_a_normal_session_without_a_token_is_unaffected(full_access_user, organization):
    """force_authenticate bypasses APITokenAuthentication entirely (no
    request.api_token set) -- the same shape as a real JWT session."""
    client = APIClient()
    client.force_authenticate(user=full_access_user)
    response = client.post("/api/v1/nodes/", {"organization": str(organization.uuid), "name": "jwt-session", "hostname": "jwt.local"}, format="json")
    assert response.status_code == 201
