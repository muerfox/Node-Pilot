"""
BackupTarget.config now routinely carries real S3/MinIO/Ceph credentials
(access_key_id/secret_access_key) -- same class of leak the security
review found and fixed for Webhook.secret: it must not be re-exposed in
plaintext on every list/retrieve, only in the create response.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_secret_access_key_is_masked_on_list(user, organization, grant_permission):
    from apps.backups.models import BackupTarget
    from apps.organizations.models import Membership

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.view")
    BackupTarget.objects.create(
        organization=organization, name="s3-backups", type="S3",
        config={"bucket": "nodepilot", "access_key_id": "AKIAEXAMPLE1234", "secret_access_key": "supersecretvalue"},
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get("/api/v1/backup-targets/")

    assert response.status_code == 200
    config = response.data["results"][0]["config"]
    assert config["bucket"] == "nodepilot"  # non-sensitive, shown as-is
    assert "supersecretvalue" not in config["secret_access_key"]
    assert config["secret_access_key"].endswith("alue")  # last 4 chars kept for identification
    assert "AKIAEXAMPLE1234" not in config["access_key_id"]


def test_create_response_returns_the_full_unmasked_config(user, organization, grant_permission):
    from apps.organizations.models import Membership

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.create")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/v1/backup-targets/",
        {
            "organization": str(organization.uuid), "name": "s3-backups", "type": "S3",
            "config": {"bucket": "nodepilot", "access_key_id": "AKIAEXAMPLE1234", "secret_access_key": "supersecretvalue"},
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["config"]["secret_access_key"] == "supersecretvalue"


def test_update_can_still_rotate_the_credential(user, organization, grant_permission):
    from apps.backups.models import BackupTarget
    from apps.organizations.models import Membership

    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "backup.create")
    target = BackupTarget.objects.create(
        organization=organization, name="s3-backups", type="S3",
        config={"bucket": "nodepilot", "access_key_id": "old-key", "secret_access_key": "old-secret"},
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(
        f"/api/v1/backup-targets/{target.uuid}/",
        {"config": {"bucket": "nodepilot", "access_key_id": "new-key", "secret_access_key": "new-secret"}},
        format="json",
    )

    assert response.status_code == 200
    target.refresh_from_db()
    assert target.config["secret_access_key"] == "new-secret"  # actually persisted, not silently dropped
