"""
AgentImageDownloadView is the backend half of fixing "deploying a VM
from a Template produces a blank disk" -- Template.image was never
referenced anywhere in provisioning, and the agent had no way to fetch
an image's bytes at all. This covers the new agent-authenticated
download endpoint, in particular that it never lets one organization's
agent fetch another organization's private image.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.images.models import Image, ImageStatus
from apps.nodes.models import Agent
from apps.storage.models import StoragePool

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent_client(node):
    agent = Agent.objects.create(node=node)
    raw_token = agent.rotate_token()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Agent {raw_token}")
    return client


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def image(organization, storage, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    img = Image.objects.create(
        organization=organization, storage=storage, name="Ubuntu 24.04", type="QCOW2", format="qcow2",
        status=ImageStatus.READY, sha256="abc123", size_bytes=9,
    )
    from apps.images import storage_backend

    path = storage_backend.final_path(img)
    path.write_bytes(b"fake-img")
    return img


def test_the_owning_organizations_agent_can_download_the_image(agent_client, image):
    response = agent_client.get(f"/api/v1/agent/images/{image.uuid}/download/")
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"fake-img"
    assert response["X-Image-Sha256"] == "abc123"
    assert response["X-Image-Format"] == "qcow2"


def test_a_different_organizations_agent_cannot_download_the_image(image, settings):
    from apps.organizations.models import Organization

    other_org = Organization.objects.create(name="Other Org", slug="other-org")
    from apps.nodes.models import Node

    other_node = Node.objects.create(organization=other_org, name="other-node", hostname="other.local")
    other_agent = Agent.objects.create(node=other_node)
    raw_token = other_agent.rotate_token()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Agent {raw_token}")

    response = client.get(f"/api/v1/agent/images/{image.uuid}/download/")
    assert response.status_code == 404  # not 403 -- existence isn't confirmed either


def test_a_human_user_cannot_use_this_endpoint(user, image):
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/v1/agent/images/{image.uuid}/download/")
    assert response.status_code in (401, 403)


def test_downloading_a_not_ready_image_is_rejected(agent_client, organization, storage):
    pending = Image.objects.create(organization=organization, storage=storage, name="still-uploading", type="QCOW2", status=ImageStatus.UPLOADING)
    response = agent_client.get(f"/api/v1/agent/images/{pending.uuid}/download/")
    assert response.status_code == 409


def test_an_unrecognized_token_is_rejected(image):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Agent not-a-real-token")
    response = client.get(f"/api/v1/agent/images/{image.uuid}/download/")
    # 403, not 401: AgentTokenAuthentication (like the existing
    # Heartbeat/VMMetricsIngest agent endpoints) doesn't implement
    # authenticate_header(), so DRF's default exception handling can't
    # emit a compliant 401 WWW-Authenticate challenge and falls back to
    # 403 -- this is existing, established behavior, not new here.
    assert response.status_code == 403
