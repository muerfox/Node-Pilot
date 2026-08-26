"""
Agent configuration. Loaded from environment variables, optionally backed
by a YAML config file (default /etc/nodepilot/agent.yaml) for the
package/systemd install path. Environment variables always take
precedence, so a systemd EnvironmentFile can override the config file.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("/etc/nodepilot/agent.yaml")


@dataclasses.dataclass
class AgentConfig:
    controller_url: str
    node_id: str
    agent_token: str
    agent_version: str = "1.0.0"
    protocol_version: str = "1.0"

    heartbeat_interval_seconds: int = 10
    reconnect_backoff_seconds: float = 2.0
    reconnect_backoff_max_seconds: float = 60.0

    tls_verify: bool = True
    ca_bundle_path: str | None = None

    storage_pool_root: str = "/var/lib/nodepilot/pools"
    cloud_init_workdir: str = "/var/lib/nodepilot/cloud-init"
    log_level: str = "INFO"

    @property
    def controller_ws_url(self) -> str:
        base = self.controller_url.rstrip("/")
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}/ws/agent/{self.node_id}/?token={self.agent_token}"

    @property
    def controller_heartbeat_url(self) -> str:
        return f"{self.controller_url.rstrip('/')}/api/v1/agent/heartbeat/"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def load_config(config_path: str | None = None) -> AgentConfig:
    file_values = _load_yaml(Path(config_path) if config_path else DEFAULT_CONFIG_PATH)

    def get(key: str, default=None, cast=str):
        env_key = f"NODEPILOT_AGENT_{key.upper()}"
        if env_key in os.environ:
            raw = os.environ[env_key]
            if cast is bool:
                return raw.strip().lower() in {"1", "true", "yes", "on"}
            return cast(raw)
        if key in file_values:
            return file_values[key]
        return default

    controller_url = get("controller_url")
    node_id = get("node_id")
    agent_token = get("agent_token") or get("token")

    if not controller_url or not node_id or not agent_token:
        raise SystemExit(
            "Missing required agent configuration. Set NODEPILOT_AGENT_CONTROLLER_URL, "
            "NODEPILOT_AGENT_NODE_ID and NODEPILOT_AGENT_AGENT_TOKEN (or provide "
            f"{DEFAULT_CONFIG_PATH} with controller_url/node_id/agent_token). "
            "Run `nodepilot agent register` on the controller to obtain a token."
        )

    return AgentConfig(
        controller_url=controller_url,
        node_id=node_id,
        agent_token=agent_token,
        agent_version=get("agent_version", "1.0.0"),
        heartbeat_interval_seconds=get("heartbeat_interval_seconds", 10, int),
        tls_verify=get("tls_verify", True, bool),
        ca_bundle_path=get("ca_bundle_path"),
        storage_pool_root=get("storage_pool_root", "/var/lib/nodepilot/pools"),
        cloud_init_workdir=get("cloud_init_workdir", "/var/lib/nodepilot/cloud-init"),
        log_level=get("log_level", "INFO"),
    )
