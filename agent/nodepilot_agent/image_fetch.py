"""
Fetches an image's bytes from the controller (section 15/16) so a new VM
disk can be seeded from it when deploying from a Template. Images live
centrally on the controller's own managed storage, never on a specific
node (apps.images.storage_backend), so this works identically regardless
of which node's storage pool the new disk lands on -- the agent just
downloads over the same agent-token-authenticated HTTP channel it
already uses for heartbeats.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile

import httpx

from nodepilot_agent.storage.base import StorageOperationError

_CHUNK_SIZE = 4 * 1024 * 1024


def download_image(config, image_uuid: str, expected_sha256: str = "") -> str:
    """Downloads the image to a local temp file, verifying its checksum
    if one was provided. Returns the temp file's path. The caller owns
    cleanup -- remove the file's parent directory once done with it
    (see disk_ops._seed_from_image)."""
    url = f"{config.controller_url.rstrip('/')}/api/v1/agent/images/{image_uuid}/download/"
    headers = {"Authorization": f"Agent {config.agent_token}"}

    tmp_dir = tempfile.mkdtemp(prefix="nodepilot-image-")
    path = os.path.join(tmp_dir, "image")
    digest = hashlib.sha256()
    try:
        with httpx.Client(verify=config.tls_verify, timeout=60.0) as client:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise StorageOperationError(f"Failed to download image {image_uuid}: HTTP {response.status_code}")
                with open(path, "wb") as out:
                    for chunk in response.iter_bytes(_CHUNK_SIZE):
                        out.write(chunk)
                        digest.update(chunk)
    except httpx.HTTPError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise StorageOperationError(f"Failed to download image {image_uuid}: {exc}") from exc
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    actual_sha256 = digest.hexdigest()
    if expected_sha256 and expected_sha256.lower() != actual_sha256:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise StorageOperationError(f"Image {image_uuid} checksum mismatch: expected {expected_sha256}, got {actual_sha256}")

    return path
