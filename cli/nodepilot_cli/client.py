"""
Thin REST client. Every command in nodepilot_cli.commands goes through
this -- the CLI never touches the database directly (section 60), it
always speaks the same versioned HTTP API a browser or automation script
would use.
"""
from __future__ import annotations

import httpx

from nodepilot_cli.config import CLIConfig


class APIError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


class NodePilotClient:
    def __init__(self, config: CLIConfig):
        self.config = config
        if not config.token:
            raise RuntimeError("Not authenticated. Run `nodepilot login` first, or set NODEPILOT_TOKEN.")
        self._client = httpx.Client(
            base_url=config.api_url.rstrip("/") + "/",
            headers={"Authorization": f"{config.token_type} {config.token}"},
            verify=config.verify_tls,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NodePilotClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs) -> dict:
        response = self._client.request(method, path.lstrip("/"), **kwargs)
        if response.status_code >= 400:
            self._raise_for_error(response)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def get(self, path: str, **kwargs) -> dict:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, json: dict | None = None, **kwargs) -> dict:
        return self.request("POST", path, json=json, **kwargs)

    def delete(self, path: str, **kwargs) -> dict:
        return self.request("DELETE", path, **kwargs)

    def paginate(self, path: str, **kwargs):
        next_path = path
        params = kwargs.pop("params", None)
        while next_path:
            data = self.get(next_path, params=params, **kwargs)
            params = None  # `next` already encodes the query string
            yield from data.get("results", [])
            next_url = data.get("next")
            next_path = next_url.split("/api/v1/", 1)[-1] if next_url else None

    @staticmethod
    def _raise_for_error(response: httpx.Response) -> None:
        try:
            body = response.json()
            error = body.get("error", {})
            raise APIError(response.status_code, error.get("code", "UNKNOWN"), error.get("message", response.text), error.get("details"))
        except ValueError:
            raise APIError(response.status_code, "UNKNOWN", response.text)
