import httpx
import pytest

from nodepilot_cli.client import APIError, NodePilotClient
from nodepilot_cli.config import CLIConfig


def _client_with_transport(handler) -> NodePilotClient:
    config = CLIConfig(api_url="https://controller.example/api/v1", token="npt_test")
    client = NodePilotClient(config)
    client._client = httpx.Client(base_url=config.api_url.rstrip("/") + "/", transport=httpx.MockTransport(handler))
    return client


def test_get_returns_json_body():
    def handler(request):
        assert request.url.path == "/api/v1/vms/"
        return httpx.Response(200, json={"count": 1, "results": [{"uuid": "1"}]})

    client = _client_with_transport(handler)
    data = client.get("vms/")
    assert data["results"][0]["uuid"] == "1"


def test_error_response_raises_api_error():
    def handler(request):
        return httpx.Response(403, json={"error": {"code": "PERMISSION_DENIED", "message": "nope", "details": {}}})

    client = _client_with_transport(handler)
    with pytest.raises(APIError) as exc_info:
        client.get("vms/")
    assert exc_info.value.code == "PERMISSION_DENIED"
    assert exc_info.value.status_code == 403


def test_paginate_follows_next_links():
    pages = {
        "vms/": httpx.Response(200, json={"results": [{"uuid": "1"}], "next": "https://controller.example/api/v1/vms/?page=2"}),
        "vms/?page=2": httpx.Response(200, json={"results": [{"uuid": "2"}], "next": None}),
    }

    def handler(request):
        key = request.url.path.lstrip("/").replace("api/v1/", "")
        if request.url.query:
            key += "?" + request.url.query.decode()
        return pages[key]

    client = _client_with_transport(handler)
    results = list(client.paginate("vms/"))
    assert [r["uuid"] for r in results] == ["1", "2"]


def test_requires_token():
    with pytest.raises(RuntimeError):
        NodePilotClient(CLIConfig(api_url="https://x", token=None))
