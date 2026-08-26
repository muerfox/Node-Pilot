"""
Chunked upload handling for the image/ISO library (section 15). Images are
landed in the controller's own managed storage (MEDIA_ROOT/images/) and
served to node agents over an authenticated HTTPS download endpoint --
this avoids ever giving the controller direct filesystem access to a
hypervisor's local disks, and avoids the agent needing inbound access to
the controller beyond the existing agent protocol.

Every read/write here is chunked; nothing loads a whole image into memory.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from django.conf import settings

from apps.common.exceptions import NodePilotAPIException

CHUNK_READ_SIZE = 4 * 1024 * 1024  # 4 MB


class UploadOutOfOrder(NodePilotAPIException):
    code_name = "UPLOAD_CHUNK_OUT_OF_ORDER"
    status_code = 409
    default_detail = "Chunk index does not match the next expected chunk for this upload session."


class UploadSizeMismatch(NodePilotAPIException):
    code_name = "UPLOAD_SIZE_MISMATCH"
    status_code = 400
    default_detail = "The uploaded bytes do not match the declared total size."


class ChecksumMismatch(NodePilotAPIException):
    code_name = "CHECKSUM_MISMATCH"
    status_code = 400
    default_detail = "The computed checksum does not match the expected checksum."


def _chunk_dir() -> Path:
    path = Path(settings.NODEPILOT["IMAGE_UPLOAD_CHUNK_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _images_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / "images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_path(session) -> Path:
    # Filename is derived entirely from our own UUID -- never from
    # user-supplied input -- so path traversal is not reachable here.
    return _chunk_dir() / session.temp_filename


def final_path(image) -> Path:
    extension = (image.format or image.type or "img").lower()
    return _images_dir() / f"{image.uuid}.{extension}"


def write_chunk(session, index: int, uploaded_file) -> int:
    if index != session.next_chunk_index:
        raise UploadOutOfOrder(f"Expected chunk {session.next_chunk_index}, got {index}.")

    destination = temp_path(session)
    mode = "ab" if destination.exists() else "wb"
    written = 0
    with open(destination, mode) as out:
        for block in uploaded_file.chunks(chunk_size=CHUNK_READ_SIZE):
            out.write(block)
            written += len(block)

    session.received_bytes += written
    session.next_chunk_index += 1
    session.save(update_fields=["received_bytes", "next_chunk_index"])
    return written


def finalize_upload(session) -> tuple[str, int]:
    """Streams the assembled file to compute its sha256, verifies size (and
    checksum, if one was declared), and moves it into place. Returns
    (sha256, size_bytes)."""
    source = temp_path(session)
    if not source.exists():
        raise NodePilotAPIException("No chunks were uploaded for this session.", code_name="UPLOAD_EMPTY", status_code=400)

    actual_size = source.stat().st_size
    if actual_size != session.total_size_bytes:
        raise UploadSizeMismatch(details={"expected": session.total_size_bytes, "actual": actual_size})

    digest = hashlib.sha256()
    with open(source, "rb") as fh:
        while True:
            block = fh.read(CHUNK_READ_SIZE)
            if not block:
                break
            digest.update(block)
    checksum = digest.hexdigest()

    if session.expected_sha256 and session.expected_sha256.lower() != checksum:
        raise ChecksumMismatch(details={"expected": session.expected_sha256, "actual": checksum})

    destination = final_path(session.image)
    os.replace(source, destination)
    return checksum, actual_size


def delete_image_file(image) -> None:
    path = final_path(image)
    if path.exists():
        path.unlink()


def abort_upload(session) -> None:
    path = temp_path(session)
    if path.exists():
        path.unlink()
