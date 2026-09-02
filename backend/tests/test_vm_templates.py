"""
Template.image (a required FK, e.g. "Ubuntu 24.04") was never referenced
anywhere in VM provisioning -- deploying "from a template" produced a
completely blank, empty disk regardless of which image the template
named. This covers the fix: VMDisk.source_image is set when a disk
should be seeded from an image, and provision_vm's CREATE_DISK step
forwards that through to the agent (which downloads and qemu-img
converts it -- see agent/tests/test_disk_ops.py and
agent/tests/test_image_fetch.py for that half).
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.images.models import Image, ImageStatus
from apps.networks.models import Network
from apps.organizations.models import Membership
from apps.storage.models import StoragePool
from apps.virtual_machines import tasks
from apps.virtual_machines.models import VirtualMachine
from apps.vm_templates.models import Template
from apps.vm_templates.services import TemplateImageNotReady, create_vm_from_template

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def network(node):
    return Network.objects.create(node=node, name="prod", bridge="vmbr0")


@pytest.fixture
def image(organization, storage):
    return Image.objects.create(organization=organization, storage=storage, name="Ubuntu 24.04", type="QCOW2", format="qcow2", status=ImageStatus.READY, sha256="deadbeef")


@pytest.fixture
def template(organization, image):
    return Template.objects.create(organization=organization, image=image, name="ubuntu-2404")


def test_create_vm_from_template_seeds_the_boot_disk_from_the_image(template, project, node, storage, network, user):
    vm, job = create_vm_from_template(template, project=project, name="web-01", storage=storage, network=network, created_by=user, node=node)

    disk = vm.disks.get()
    assert disk.source_image_id == template.image_id
    assert disk.size_bytes == template.default_disk_gb * 1024**3


def test_create_vm_from_template_rejects_a_not_ready_image(organization, storage, network, project, user):
    unready_image = Image.objects.create(organization=organization, storage=storage, name="still-uploading", type="QCOW2", status=ImageStatus.UPLOADING)
    broken_template = Template.objects.create(organization=organization, image=unready_image, name="broken")

    with pytest.raises(TemplateImageNotReady):
        create_vm_from_template(broken_template, project=project, name="web-01", storage=storage, network=network, created_by=user)


def _fake_agent(monkeypatch, responses=None):
    calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append((operation.value, payload, timeout))
        if responses and operation.value in responses:
            return responses[operation.value]
        return {"volume_id": "/pools/local/x.qcow2", "device": "vda", "format": "qcow2"}

    monkeypatch.setattr(tasks.agent_client, "send_operation", fake_send_operation)
    return calls


def test_provision_vm_forwards_the_image_to_create_disk_with_a_generous_timeout(template, project, node, storage, network, user, monkeypatch):
    calls = _fake_agent(monkeypatch)
    vm, job = create_vm_from_template(template, project=project, name="web-01", storage=storage, network=network, created_by=user, node=node)

    tasks.provision_vm(job.pk, vm.pk)

    create_disk_calls = [(payload, timeout) for name, payload, timeout in calls if name == "CREATE_DISK"]
    assert len(create_disk_calls) == 1
    payload, timeout = create_disk_calls[0]
    assert payload["image_uuid"] == str(template.image.uuid)
    assert payload["image_sha256"] == "deadbeef"
    assert payload["image_format"] == "qcow2"
    assert timeout == 3600  # default 30s AGENT_RPC_TIMEOUT_SECONDS is nowhere near enough


def test_provision_vm_does_not_send_image_fields_for_a_plain_vm(organization, project, node, storage, network, user, monkeypatch):
    from apps.virtual_machines import services

    calls = _fake_agent(monkeypatch)
    vm, job = services.create_vm(
        organization=organization, project=project, name="plain", created_by=user, node=node,
        disks=[{"storage": storage, "name": "root", "size_bytes": 10 * 1024**3, "bootable": True}],
        nics=[], cpu_count=1, memory_mb=1024,
    )

    tasks.provision_vm(job.pk, vm.pk)

    create_disk_calls = [(payload, timeout) for name, payload, timeout in calls if name == "CREATE_DISK"]
    assert len(create_disk_calls) == 1
    payload, timeout = create_disk_calls[0]
    assert "image_uuid" not in payload
    assert timeout is None


def test_deploy_endpoint_creates_a_vm_with_the_templates_image(user, organization, template, node, storage, network, project, grant_permission, monkeypatch):
    _fake_agent(monkeypatch)
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "vm.create")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        f"/api/v1/templates/{template.uuid}/deploy/",
        {"name": "web-02", "project": str(project.uuid), "storage": str(storage.uuid), "network": str(network.uuid), "node": str(node.uuid)},
        format="json",
    )

    assert response.status_code == 201
    vm = VirtualMachine.objects.get(uuid=response.data["id"])
    assert vm.disks.get().source_image_id == template.image_id
