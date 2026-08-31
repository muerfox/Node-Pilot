"""
NetworkViewSet used to be a plain ModelViewSet with no perform_create/
destroy override -- creating or deleting a Network was a database-only
operation. CREATE_NETWORK/DELETE_NETWORK were defined in the Agent
Protocol and fully implemented on the agent side
(nodepilot_agent.operations.network_ops), but nothing on the controller
ever dispatched them, so the bridge these rows claimed to represent was
never actually created (or torn down) on the hypervisor at all.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.jobs.models import JobStatus
from apps.networks.models import Network, NetworkStatus
from apps.networks.serializers import NetworkSerializer
from apps.organizations.models import Membership

pytestmark = pytest.mark.django_db


def _fake_agent(monkeypatch, *, fail=False):
    import apps.networks.tasks as tasks_module

    calls = []

    def fake_send_operation(target_node, operation, resource_id, payload=None, timeout=None):
        calls.append((operation.value, payload))
        if fail:
            raise RuntimeError("agent unreachable")
        return {}

    monkeypatch.setattr(tasks_module.agent_client, "send_operation", fake_send_operation)
    return calls


# --- service + task: create --------------------------------------------


def test_create_network_starts_inactive_until_the_agent_confirms(node, user, monkeypatch):
    from apps.networks import services, tasks

    calls = _fake_agent(monkeypatch)
    network, job = services.create_network(node=node, name="prod", type="BRIDGE", bridge="vmbr0", vlan_id=None, dhcp_enabled=False, requested_by=user)
    assert network.status == NetworkStatus.INACTIVE  # not yet confirmed

    tasks.create_network_task(job.pk, network.pk)

    network.refresh_from_db()
    job.refresh_from_db()
    assert network.status == NetworkStatus.ACTIVE
    assert job.status == JobStatus.SUCCESS
    assert calls == [("CREATE_NETWORK", {"bridge": "vmbr0", "vlan_id": None})]


def test_create_network_for_a_vlan_sends_the_vlan_id(node, user, monkeypatch):
    from apps.networks import services, tasks

    calls = _fake_agent(monkeypatch)
    network, job = services.create_network(node=node, name="vlan120", type="VLAN", bridge="vmbr0", vlan_id=120, dhcp_enabled=False, requested_by=user)
    tasks.create_network_task(job.pk, network.pk)

    assert calls == [("CREATE_NETWORK", {"bridge": "vmbr0", "vlan_id": 120})]


def test_create_network_task_marks_error_on_agent_failure(node, user, monkeypatch):
    from apps.networks import services, tasks

    _fake_agent(monkeypatch, fail=True)
    network, job = services.create_network(node=node, name="prod", type="BRIDGE", bridge="vmbr0", vlan_id=None, dhcp_enabled=False, requested_by=user)

    with pytest.raises(RuntimeError):
        tasks.create_network_task(job.pk, network.pk)

    network.refresh_from_db()
    job.refresh_from_db()
    assert network.status == NetworkStatus.ERROR
    assert job.status == JobStatus.FAILED
    assert Network.objects.filter(pk=network.pk).exists()  # row is kept, not silently dropped


# --- service + task: delete --------------------------------------------


def test_delete_network_removes_the_row_only_after_the_agent_confirms(node, user, monkeypatch):
    from apps.networks import services, tasks

    calls = _fake_agent(monkeypatch)
    network = Network.objects.create(node=node, name="prod", bridge="vmbr0", status=NetworkStatus.ACTIVE)

    job = services.delete_network(network, user)
    assert Network.objects.filter(pk=network.pk).exists()  # still there -- deletion is queued, not done

    tasks.delete_network_task(job.pk, network.pk)

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS
    assert not Network.objects.filter(pk=network.pk).exists()
    assert calls == [("DELETE_NETWORK", {"bridge": "vmbr0", "vlan_id": None})]


def test_delete_network_task_keeps_the_row_on_agent_failure(node, user, monkeypatch):
    from apps.networks import services, tasks

    _fake_agent(monkeypatch, fail=True)
    network = Network.objects.create(node=node, name="prod", bridge="vmbr0", status=NetworkStatus.ACTIVE)
    job = services.delete_network(network, user)

    with pytest.raises(RuntimeError):
        tasks.delete_network_task(job.pk, network.pk)

    network.refresh_from_db()
    job.refresh_from_db()
    assert network.status == NetworkStatus.ERROR
    assert job.status == JobStatus.FAILED
    assert Network.objects.filter(pk=network.pk).exists()  # a failed teardown must not silently disappear


# --- serializer validation ----------------------------------------------


@pytest.mark.parametrize("bridge", ["vmbr0", "br-lan", "eth0.10"])
def test_valid_bridge_names_pass(bridge):
    serializer = NetworkSerializer(data={"bridge": bridge}, partial=True)
    serializer.is_valid()
    assert "bridge" not in serializer.errors


@pytest.mark.parametrize("bridge", ["", "vmbr0; rm -rf /", "a" * 20, "vm br0"])
def test_invalid_bridge_names_are_rejected(bridge):
    serializer = NetworkSerializer(data={"bridge": bridge}, partial=True)
    assert not serializer.is_valid()
    assert "bridge" in serializer.errors


@pytest.mark.parametrize("vlan_id", [0, 4095, -1])
def test_out_of_range_vlan_id_is_rejected(vlan_id):
    serializer = NetworkSerializer(data={"vlan_id": vlan_id}, partial=True)
    assert not serializer.is_valid()
    assert "vlan_id" in serializer.errors


def test_bridge_too_long_to_combine_with_a_vlan_id_is_rejected(node):
    # "vmbr0extra" (10 chars) is a valid bridge name on its own, but
    # combined with a 4-digit vlan_id it would need a 16-char dedicated
    # bridge device name ("vmbr0extra.4094b") -- one over IFNAMSIZ.
    data = {"node": str(node.uuid), "name": "x", "type": "VLAN", "bridge": "vmbr0extra", "vlan_id": 4094}
    serializer = NetworkSerializer(data=data)
    assert not serializer.is_valid()
    assert "bridge" in serializer.errors


def test_bridge_that_fits_with_a_vlan_id_is_accepted(node):
    data = {"node": str(node.uuid), "name": "x", "type": "VLAN", "bridge": "vmbr0", "vlan_id": 4094}
    serializer = NetworkSerializer(data=data)
    assert serializer.is_valid(), serializer.errors


# --- API-level ------------------------------------------------------------


def test_creating_a_network_through_the_api_dispatches_the_job(user, organization, node, grant_permission, monkeypatch):
    _fake_agent(monkeypatch)
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "network.manage")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post("/api/v1/networks/", {"node": str(node.uuid), "name": "prod", "type": "BRIDGE", "bridge": "vmbr0"}, format="json")

    assert response.status_code == 201
    assert response.data["status"] == NetworkStatus.INACTIVE


def test_updating_a_network_through_the_api_is_not_allowed(user, organization, node, grant_permission):
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "network.manage")
    network = Network.objects.create(node=node, name="prod", bridge="vmbr0")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.patch(f"/api/v1/networks/{network.uuid}/", {"bridge": "vmbr1"}, format="json")

    assert response.status_code == 405
    network.refresh_from_db()
    assert network.bridge == "vmbr0"  # unchanged


def test_deleting_a_network_through_the_api_returns_a_job_not_204(user, organization, node, grant_permission, monkeypatch):
    _fake_agent(monkeypatch)
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "network.manage")
    network = Network.objects.create(node=node, name="prod", bridge="vmbr0")

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.delete(f"/api/v1/networks/{network.uuid}/")

    assert response.status_code == 202
    assert "job_id" in response.data
    assert Network.objects.filter(pk=network.pk).exists()  # deletion is queued, not immediate
