import pytest

from apps.organizations.models import Organization
from apps.permissions.policies import has_permission, organizations_with_permission

pytestmark = pytest.mark.django_db


def test_user_without_grant_is_denied(user, organization):
    assert has_permission(user, organization, "vm.create") is False


def test_grant_allows_specific_permission(user, organization, grant_permission):
    grant_permission(user, organization, "vm.create")
    assert has_permission(user, organization, "vm.create") is True
    assert has_permission(user, organization, "vm.delete") is False  # not granted


def test_grant_is_scoped_to_its_organization(user, organization, grant_permission):
    other_org = Organization.objects.create(name="Other", slug="other")
    grant_permission(user, organization, "vm.create")
    assert has_permission(user, other_org, "vm.create") is False


def test_none_organization_denies_non_superuser(user):
    assert has_permission(user, None, "vm.create") is False


def test_superuser_bypasses_everything(superuser, organization):
    assert has_permission(superuser, organization, "vm.delete") is True
    assert has_permission(superuser, None, "organization.manage") is True


def test_organizations_with_permission_filters_correctly(user, organization, grant_permission):
    other_org = Organization.objects.create(name="Other", slug="other")
    grant_permission(user, organization, "vm.view")
    allowed = organizations_with_permission(user, "vm.view", [organization.pk, other_org.pk])
    assert allowed == {organization.pk}
