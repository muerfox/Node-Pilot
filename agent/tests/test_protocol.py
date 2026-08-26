from nodepilot_agent.protocol import AgentRequest, AgentResponse, OperationType


def test_agent_request_roundtrip():
    wire = {"request_id": "abc123", "operation": "START_VM", "resource_id": "vm-1", "payload": {"foo": "bar"}}
    request = AgentRequest.from_wire(wire)
    assert request.operation == OperationType.START_VM
    assert request.resource_id == "vm-1"
    assert request.payload == {"foo": "bar"}


def test_agent_response_ok():
    response = AgentResponse.ok("req-1", {"volume_id": "/x"})
    wire = response.to_wire()
    assert wire == {"request_id": "req-1", "success": True, "data": {"volume_id": "/x"}, "error": None}


def test_agent_response_fail():
    response = AgentResponse.fail("req-2", "boom")
    wire = response.to_wire()
    assert wire["success"] is False
    assert wire["error"] == "boom"


def test_no_shell_execute_operation_exists():
    """Structural guarantee (section 4): there is no generic
    shell-execution operation in the protocol, and never should be."""
    names = {op.value for op in OperationType}
    forbidden = {"EXECUTE_SHELL", "RUN_COMMAND", "EXEC", "SHELL"}
    assert not (names & forbidden)
