import pytest

from nodepilot_agent.config import load_config


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NODEPILOT_AGENT_CONTROLLER_URL", "https://controller.example")
    monkeypatch.setenv("NODEPILOT_AGENT_NODE_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("NODEPILOT_AGENT_AGENT_TOKEN", "npa_secret")

    config = load_config(str(tmp_path / "does-not-exist.yaml"))

    assert config.controller_url == "https://controller.example"
    assert config.node_id == "11111111-1111-1111-1111-111111111111"
    assert config.agent_token == "npa_secret"
    assert config.controller_ws_url.startswith("wss://controller.example/ws/agent/")
    assert "token=npa_secret" in config.controller_ws_url
    assert config.controller_heartbeat_url == "https://controller.example/api/v1/agent/heartbeat/"


def test_load_config_missing_required_fields_exits(monkeypatch, tmp_path):
    monkeypatch.delenv("NODEPILOT_AGENT_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("NODEPILOT_AGENT_NODE_ID", raising=False)
    monkeypatch.delenv("NODEPILOT_AGENT_AGENT_TOKEN", raising=False)
    monkeypatch.delenv("NODEPILOT_AGENT_TOKEN", raising=False)

    with pytest.raises(SystemExit):
        load_config(str(tmp_path / "does-not-exist.yaml"))
