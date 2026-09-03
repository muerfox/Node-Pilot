"""
The chunked image upload flow (InitiateUploadView/ChunkUploadView/
FinalizeUploadView/AbortUploadView) had zero test coverage. Tracing it
surfaced two real bugs:

1. FinalizeUploadView had no idempotency guard. finalize_upload() moves
   the assembled temp file into its final location on success, so a
   second call (a client retry after a response that timed out even
   though the first call actually succeeded) finds no temp file, raises
   "no chunks uploaded", and the view's except-handler marked the
   already-successfully-uploaded Image FAILED -- silently breaking a
   perfectly good, possibly already-in-use image.

2. ChunkUploadView had no locking around write_chunk's read-check-write-
   increment sequence, so two concurrent PUTs for the same session (a
   realistic client/proxy retry racing the still-in-flight original, not
   just malice) could both pass the next_chunk_index check and both
   write into the same destination file.
"""
from __future__ import annotations

import hashlib

import pytest
from rest_framework.test import APIClient

from apps.common.locks import RedisLock
from apps.images.models import Image, ImageStatus, ImageUploadSession, UploadStatus
from apps.organizations.models import Membership
from apps.storage.models import StoragePool

pytestmark = pytest.mark.django_db


@pytest.fixture
def storage(node):
    return StoragePool.objects.create(node=node, name="local", type="DIRECTORY", path="/pools/local")


@pytest.fixture
def client(user, organization, grant_permission):
    Membership.objects.create(user=user, organization=organization)
    grant_permission(user, organization, "image.upload", "image.view")
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _initiate(client, storage, *, total_size_bytes: int, expected_sha256: str = "") -> dict:
    response = client.post(
        "/api/v1/images/uploads/",
        {"name": "ubuntu-24.04", "type": "QCOW2", "storage": str(storage.uuid), "total_size_bytes": total_size_bytes, "expected_sha256": expected_sha256},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


def _put_chunk(client, session_uuid, index: int, content: bytes):
    return client.put(
        f"/api/v1/images/uploads/{session_uuid}/chunk/?index={index}", data=content, content_type="application/octet-stream",
        HTTP_CONTENT_DISPOSITION='attachment; filename="chunk.bin"',
    )


CONTENT = b"fake qcow2 bytes " * 1000


def _upload_full_content(client, storage, content: bytes = CONTENT, expected_sha256: str = ""):
    data = _initiate(client, storage, total_size_bytes=len(content), expected_sha256=expected_sha256)
    session_uuid = data["uuid"]
    chunk_response = _put_chunk(client, session_uuid, 0, content)
    assert chunk_response.status_code == 200, chunk_response.data
    return session_uuid


# --- ImageSerializer.Meta.fields was missing `storage` --------------------
#
# ImageSerializer declared `storage` as a field but never listed it in
# Meta.fields -- DRF's ModelSerializer treats that as a hard error (not a
# silently-dropped field), so *every* serialization of an Image crashed
# with a 500, including the most basic read paths: listing and
# retrieving images through ImageViewSet.


def test_listing_images_does_not_500(client, storage, organization):
    Image.objects.create(organization=organization, storage=storage, name="preexisting", type="QCOW2", status=ImageStatus.READY)

    response = client.get("/api/v1/images/")

    assert response.status_code == 200
    assert response.data["results"][0]["storage"] == storage.uuid


def test_retrieving_a_single_image_does_not_500(client, storage, organization):
    image = Image.objects.create(organization=organization, storage=storage, name="preexisting", type="QCOW2", status=ImageStatus.READY)

    response = client.get(f"/api/v1/images/{image.uuid}/")

    assert response.status_code == 200
    assert response.data["storage"] == storage.uuid


# --- happy path -----------------------------------------------------------


def test_full_upload_flow_marks_the_image_ready(client, storage):
    session_uuid = _upload_full_content(client, storage)

    response = client.post(f"/api/v1/images/uploads/{session_uuid}/finalize/")
    assert response.status_code == 200
    assert response.data["status"] == ImageStatus.READY
    assert response.data["sha256"] == hashlib.sha256(CONTENT).hexdigest()

    session = ImageUploadSession.objects.get(uuid=session_uuid)
    assert session.status == UploadStatus.COMPLETED


def test_finalize_verifies_the_expected_checksum(client, storage):
    session_uuid = _upload_full_content(client, storage, expected_sha256="0" * 64)

    response = client.post(f"/api/v1/images/uploads/{session_uuid}/finalize/")
    assert response.status_code == 400

    image = ImageUploadSession.objects.get(uuid=session_uuid).image
    assert image.status == ImageStatus.FAILED


# --- bug #1: finalize idempotency -----------------------------------------


def test_finalizing_twice_does_not_flip_a_successful_image_to_failed(client, storage):
    session_uuid = _upload_full_content(client, storage)

    first = client.post(f"/api/v1/images/uploads/{session_uuid}/finalize/")
    assert first.status_code == 200
    assert first.data["status"] == ImageStatus.READY

    # A client retry of the same request (e.g. its first response never
    # arrived) must not undo the successful upload.
    second = client.post(f"/api/v1/images/uploads/{session_uuid}/finalize/")
    assert second.status_code == 200
    assert second.data["status"] == ImageStatus.READY

    image = ImageUploadSession.objects.get(uuid=session_uuid).image
    image.refresh_from_db()
    assert image.status == ImageStatus.READY  # not FAILED


def test_finalizing_an_aborted_session_is_rejected_cleanly(client, storage):
    data = _initiate(client, storage, total_size_bytes=len(CONTENT))
    session_uuid = data["uuid"]
    _put_chunk(client, session_uuid, 0, CONTENT)

    abort_response = client.post(f"/api/v1/images/uploads/{session_uuid}/abort/")
    assert abort_response.status_code == 204

    finalize_response = client.post(f"/api/v1/images/uploads/{session_uuid}/finalize/")
    assert finalize_response.status_code == 409  # not a 500/silent state flip


# --- bug #2: concurrent chunk writes are serialized -----------------------


def test_a_chunk_write_is_rejected_while_another_is_already_in_flight_for_that_session(client, storage):
    data = _initiate(client, storage, total_size_bytes=len(CONTENT))
    session = ImageUploadSession.objects.get(uuid=data["uuid"])

    # Simulate a concurrent PUT already holding the per-session lock.
    lock = RedisLock(f"image-upload:{session.uuid}", ttl_seconds=60)
    assert lock.acquire(blocking=False)
    try:
        response = _put_chunk(client, session.uuid, 0, CONTENT)
        assert response.status_code == 409
        assert response.data["error"]["code"] == "UPLOAD_BUSY"
    finally:
        lock.release()

    # Once released, the same chunk goes through normally.
    response = _put_chunk(client, session.uuid, 0, CONTENT)
    assert response.status_code == 200


# --- other existing behavior, now with real coverage ----------------------


def test_chunk_out_of_order_is_rejected(client, storage):
    data = _initiate(client, storage, total_size_bytes=len(CONTENT))
    response = _put_chunk(client, data["uuid"], 1, CONTENT)  # should be 0
    assert response.status_code == 409


def test_chunk_after_the_session_is_no_longer_uploading_is_rejected(client, storage):
    data = _initiate(client, storage, total_size_bytes=len(CONTENT))
    client.post(f"/api/v1/images/uploads/{data['uuid']}/abort/")

    response = _put_chunk(client, data["uuid"], 0, CONTENT)
    assert response.status_code == 409


def test_a_different_users_session_is_not_accessible(storage, organization, grant_permission):
    from apps.users.models import User

    owner = User.objects.create_user(username="owner", email="owner@example.com", password="x")
    Membership.objects.create(user=owner, organization=organization)
    grant_permission(owner, organization, "image.upload")
    owner_client = APIClient()
    owner_client.force_authenticate(user=owner)
    data = _initiate(owner_client, storage, total_size_bytes=len(CONTENT))

    intruder = User.objects.create_user(username="intruder", email="intruder@example.com", password="x")
    intruder_client = APIClient()
    intruder_client.force_authenticate(user=intruder)
    response = _put_chunk(intruder_client, data["uuid"], 0, CONTENT)
    assert response.status_code == 404
