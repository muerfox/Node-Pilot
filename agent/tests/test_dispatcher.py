import pytest

from nodepilot_agent.config import AgentConfig
from nodepilot_agent.operations import vm_ops
from nodepilot_agent.operations.dispatcher import Dispatcher
from nodepilot_agent.protocol import AgentRequest, OperationType


@pytest.fixture
def config():
    return AgentConfig(controller_url="https://controller.example", node_id="node-1", agent_token="tok")


@pytest.fixture
def dispatcher(config):
    async def fake_send_console_data(session_id, data_b64):
        pass

    return Dispatcher(config, libvirt_client=object(), send_console_data=fake_send_console_data)


async def test_dispatch_routes_start_vm(dispatcher, monkeypatch):
    called = {}

    def fake_start_vm(resource_id, libvirt_client):
        called["resource_id"] = resource_id
        return {}

    monkeypatch.setattr(vm_ops, "start_vm", fake_start_vm)

    request = AgentRequest(request_id="r1", operation=OperationType.START_VM, resource_id="vm-uuid-1")
    response = await dispatcher.dispatch(request)

    assert response.success is True
    assert response.request_id == "r1"
    assert called["resource_id"] == "vm-uuid-1"


async def test_dispatch_catches_handler_exceptions_and_returns_failure(dispatcher, monkeypatch):
    def boom(resource_id, libvirt_client):
        raise RuntimeError("libvirt exploded")

    monkeypatch.setattr(vm_ops, "start_vm", boom)

    request = AgentRequest(request_id="r2", operation=OperationType.START_VM, resource_id="vm-uuid-2")
    response = await dispatcher.dispatch(request)

    assert response.success is False
    assert "libvirt exploded" in response.error


async def test_unhandled_operation_returns_failure_not_a_crash(dispatcher, monkeypatch):
    # Simulate an operation the dispatcher genuinely doesn't recognize by
    # forging a request with a raw string operation value bypassing the enum.
    request = AgentRequest(request_id="r3", operation=OperationType.MIGRATE_VM, resource_id="vm-uuid-3")
    response = await dispatcher.dispatch(request)
    assert response.success is False  # migrate_vm() raises NotImplementedError -- surfaced as a clean failure
