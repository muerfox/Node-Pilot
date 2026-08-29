import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_non_staff_user_can_resolve_a_known_username(user):
    """A regular org admin needs this to add a Membership/RoleAssignment
    without needing platform-wide user.view (staff-only)."""
    from apps.users.models import User

    target = User.objects.create_user(username="bob", email="bob@example.com", password="correct-horse-battery-staple")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/users/lookup/", {"username": "bob"})

    assert response.status_code == 200
    assert response.data == {"uuid": str(target.uuid), "username": "bob"}


def test_lookup_requires_authentication():
    client = APIClient()
    response = client.get("/api/v1/users/lookup/", {"username": "bob"})
    assert response.status_code == 401


def test_lookup_404s_for_unknown_username(user):
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/users/lookup/", {"username": "nobody"})
    assert response.status_code == 404


def test_lookup_cannot_be_used_to_list_all_users(user):
    """Confirms this doesn't become a backdoor around the staff-only
    list/retrieve endpoints -- no username means no result, and there's
    no way to enumerate."""
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/users/lookup/")
    assert response.status_code == 400
