"""
CLI configuration: API URL + credential, read from (in precedence order)
CLI flags > environment variables > ~/.config/nodepilot/config.yaml,
written by `nodepilot login`.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("NODEPILOT_CONFIG_DIR", Path.home() / ".config" / "nodepilot"))
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclasses.dataclass
class CLIConfig:
    api_url: str = "https://localhost/api/v1"
    token: str | None = None
    token_type: str = "Token"  # "Token" for an API token, "Bearer" for a JWT access token
    verify_tls: bool = True


def load_config() -> CLIConfig:
    data: dict = {}
    if CONFIG_PATH.exists():
        data = yaml.safe_load(CONFIG_PATH.read_text()) or {}

    return CLIConfig(
        api_url=os.environ.get("NODEPILOT_API_URL", data.get("api_url", "https://localhost/api/v1")),
        token=os.environ.get("NODEPILOT_TOKEN", data.get("token")),
        token_type=os.environ.get("NODEPILOT_TOKEN_TYPE", data.get("token_type", "Token")),
        verify_tls=data.get("verify_tls", True),
    )


def save_config(config: CLIConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(dataclasses.asdict(config)))
    CONFIG_PATH.chmod(0o600)  # the file holds a credential
