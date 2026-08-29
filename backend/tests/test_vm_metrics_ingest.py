import uuid

import pytest

from apps.metrics.store import get_vm_samples
from apps.nodes.models import Agent, AgentStatus
from apps.nodes.services import record_vm_metrics_batch
from apps.virtual_machines.models import VirtualMachine

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(node):
    return Agent.objects.create(node=node, agent_id=uuid.uuid4(), status=AgentStatus.ACTIVE)


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="RUNNING")


def test_records_sample_for_owned_vm(agent, vm):
    recorded = record_vm_metrics_batch(agent, [{"domain_uuid": vm.domain_uuid, "cpu_percent": 42.0, "memory_used_mb": 512}])
    assert recorded == 1

    samples = get_vm_samples(vm)
    assert len(samples) == 1
    assert samples[0]["cpu_percent"] == 42.0
    assert samples[0]["memory_used_mb"] == 512


def test_skips_unknown_domain_uuid(agent):
    recorded = record_vm_metrics_batch(agent, [{"domain_uuid": uuid.uuid4(), "cpu_percent": 10.0, "memory_used_mb": 100}])
    assert recorded == 0


def test_cannot_write_metrics_for_a_vm_on_a_different_node(agent, organization, project):
    from apps.nodes.models import Node

    other_node = Node.objects.create(organization=organization, name="node-02", hostname="node-02.local")
    other_vm = VirtualMachine.objects.create(organization=organization, project=project, node=other_node, name="db-01", status="RUNNING")

    recorded = record_vm_metrics_batch(agent, [{"domain_uuid": other_vm.domain_uuid, "cpu_percent": 99.0, "memory_used_mb": 999}])

    assert recorded == 0
    assert get_vm_samples(other_vm) == []
