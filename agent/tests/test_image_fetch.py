"""
Deploying a VM from a Template used to produce a completely blank disk --
Template.image was never referenced anywhere in VM provisioning. This
covers the agent side of the fix: fetching the image's bytes from the
controller (apps.images.views.AgentImageDownloadView on the backend)
over the same agent-token-authenticated HTTP channel already used for
heartbeats, with checksum verification before it's ever handed to
qemu-img.
"""
from __future__ import annotations

import hashlib
import os

import httpx
import pytest

from nodepilot_agent import image_fetch
from nodepilot_agent.storage.base import StorageOperationError


class _FakeConfig:
    controller_url = "https://controller.example"
    agent_token = "test-agent-token"
    tls_verify = True


def _patch_transport(monkeypatch, handler):
    real_client_cls = httpx.Client

    def fake_client(*args, **kwargs):
        return real_client_cls(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", fake_client)


def test_download_image_writes_the_bytes_and_returns_the_path(monkeypatch):
    content = b"fake qcow2 bytes" * 10_000

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/agent/images/img-1/download/"
        assert request.headers["Authorization"] == "Agent test-agent-token"
        return httpx.Response(200, content=content)

    _patch_transport(monkeypatch, handler)

    path = image_fetch.download_image(_FakeConfig(), "img-1")
    try:
        with open(path, "rb") as fh:
            assert fh.read() == content
    finally:
        os.remove(path)
        os.rmdir(os.path.dirname(path))


def test_download_image_verifies_a_matching_checksum(monkeypatch):
    content = b"known content"
    expected = hashlib.sha256(content).hexdigest()

    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=content))

    path = image_fetch.download_image(_FakeConfig(), "img-1", expected_sha256=expected)
    os.remove(path)
    os.rmdir(os.path.dirname(path))


def test_download_image_rejects_a_checksum_mismatch_and_cleans_up(monkeypatch):
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"tampered or corrupted"))

    captured_dirs = []
    real_mkdtemp = image_fetch.tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        captured_dirs.append(d)
        return d

    monkeypatch.setattr(image_fetch.tempfile, "mkdtemp", recording_mkdtemp)

    with pytest.raises(StorageOperationError, match="checksum mismatch"):
        image_fetch.download_image(_FakeConfig(), "img-1", expected_sha256="0" * 64)

    assert not os.path.exists(captured_dirs[0])  # no leaked temp file on failure


def test_download_image_raises_on_a_non_200_response(monkeypatch):
    _patch_transport(monkeypatch, lambda request: httpx.Response(404, content=b""))

    with pytest.raises(StorageOperationError, match="HTTP 404"):
        image_fetch.download_image(_FakeConfig(), "missing-image")


def test_download_image_without_an_expected_checksum_accepts_anything(monkeypatch):
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"anything"))

    path = image_fetch.download_image(_FakeConfig(), "img-1")
    os.remove(path)
    os.rmdir(os.path.dirname(path))
