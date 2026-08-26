from click.testing import CliRunner

from nodepilot_cli import main
from nodepilot_cli.commands import vm as vm_module
from nodepilot_cli.config import CLIConfig


class FakeClient:
    """Stands in for NodePilotClient inside command modules; records
    calls and returns canned responses."""

    instances: list["FakeClient"] = []

    def __init__(self, config):
        self.config = config
        self.calls: list[tuple[str, tuple, dict]] = []
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, path, json=None, **kwargs):
        self.calls.append(("post", (path,), {"json": json}))
        return {"job_id": "job-123", "status": "queued"}

    def get(self, path, **kwargs):
        self.calls.append(("get", (path,), kwargs))
        return {"uuid": "vm-1", "name": "web-01", "status": "RUNNING"}

    def delete(self, path, **kwargs):
        self.calls.append(("delete", (path,), kwargs))
        return {"job_id": "job-456", "status": "queued"}

    def paginate(self, path, **kwargs):
        self.calls.append(("paginate", (path,), kwargs))
        return iter([{"uuid": "vm-1", "name": "web-01", "status": "RUNNING", "cpu_count": 2, "memory_mb": 2048, "node": "node-1"}])


def _invoke(monkeypatch, module, args):
    FakeClient.instances.clear()
    monkeypatch.setattr(module, "NodePilotClient", FakeClient)
    runner = CliRunner()
    result = runner.invoke(main.cli, args, obj=CLIConfig(api_url="https://x/api/v1", token="npt_test"))
    return result


def test_vm_start_calls_correct_endpoint(monkeypatch):
    result = _invoke(monkeypatch, vm_module, ["vm", "start", "vm-1"])
    assert result.exit_code == 0
    assert "job_id: job-123" in result.output
    assert FakeClient.instances[0].calls[0] == ("post", ("vms/vm-1/start/",), {"json": None})


def test_vm_stop_passes_force_flag(monkeypatch):
    result = _invoke(monkeypatch, vm_module, ["vm", "stop", "vm-1", "--force"])
    assert result.exit_code == 0
    assert FakeClient.instances[0].calls[0] == ("post", ("vms/vm-1/stop/",), {"json": {"force": True}})


def test_vm_list_renders_table(monkeypatch):
    result = _invoke(monkeypatch, vm_module, ["vm", "list"])
    assert result.exit_code == 0
    assert "web-01" in result.output
    assert "RUNNING" in result.output


def test_vm_delete_requires_confirmation(monkeypatch):
    FakeClient.instances.clear()
    monkeypatch.setattr(vm_module, "NodePilotClient", FakeClient)
    runner = CliRunner()
    result = runner.invoke(main.cli, ["vm", "delete", "vm-1"], input="n\n", obj=CLIConfig(api_url="https://x/api/v1", token="npt_test"))
    assert result.exit_code != 0
    assert FakeClient.instances == []  # aborted before the client was ever used
