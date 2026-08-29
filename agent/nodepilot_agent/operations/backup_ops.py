"""
Backup/restore. LOCAL and NFS targets write directly to a filesystem
path the agent can reach; S3/MinIO/Ceph (RGW) targets all speak the S3
API, so one boto3-based implementation covers all three -- MinIO and
Ceph RGW just need `endpoint_url` set in the target's config to point at
themselves instead of AWS.
"""
from __future__ import annotations

import hashlib
import os
import tempfile

from nodepilot_agent.storage.base import StorageOperationError, run

_FILE_BASED_TARGETS = {"LOCAL", "NFS"}
_S3_COMPATIBLE_TARGETS = {"S3", "MINIO", "CEPH"}


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _s3_client(config: dict):
    try:
        import boto3
    except ImportError as exc:
        raise StorageOperationError(
            "boto3 is not installed on this agent; install the 's3' extra to use S3/MinIO/Ceph backup targets."
        ) from exc

    return boto3.client(
        "s3",
        endpoint_url=config.get("endpoint_url"),  # unset (None) -> real AWS S3; set -> MinIO/Ceph RGW/any S3-compatible endpoint
        aws_access_key_id=config.get("access_key_id"),
        aws_secret_access_key=config.get("secret_access_key"),
        region_name=config.get("region", "us-east-1"),
    )


def create_backup(payload: dict, resource_id: str) -> dict:
    target_type = payload["target_type"]
    volume_id = payload.get("volume_id")
    if not volume_id:
        raise StorageOperationError("create_backup requires the VM's primary disk volume_id in the payload.")

    if target_type in _FILE_BASED_TARGETS:
        target_dir = payload["target"]["path"]
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, f"{payload['backup_uuid']}.qcow2")
        # `-O qcow2` here is the *backup archive's* format, independent of
        # the live disk's own format (raw block device or qcow2 file) --
        # qemu-img autodetects the source format, so this works for either.
        run(["qemu-img", "convert", "-O", "qcow2", volume_id, dest])
        checksum = _sha256_file(dest)
        size_bytes = os.path.getsize(dest)
        return {"backup_ref": dest, "size_bytes": size_bytes, "checksum": checksum}

    if target_type in _S3_COMPATIBLE_TARGETS:
        config = payload["target"]
        client = _s3_client(config)
        key = f"{config.get('prefix', 'nodepilot-backups').rstrip('/')}/{payload['backup_uuid']}.qcow2"

        with tempfile.TemporaryDirectory(prefix="nodepilot-backup-") as tmpdir:
            local_path = os.path.join(tmpdir, "backup.qcow2")
            run(["qemu-img", "convert", "-O", "qcow2", volume_id, local_path])
            checksum = _sha256_file(local_path)
            size_bytes = os.path.getsize(local_path)
            # boto3's upload_file streams via its TransferManager (chunked
            # multipart for large files) -- it never loads the whole
            # backup into memory, matching the same rule chunked image
            # uploads follow on the controller side.
            client.upload_file(
                local_path, config["bucket"], key,
                ExtraArgs={"ServerSideEncryption": "AES256", "Metadata": {"sha256": checksum}},
            )
        return {"backup_ref": key, "size_bytes": size_bytes, "checksum": checksum}

    raise NotImplementedError(f"Backup target type {target_type!r} is not supported by this agent version.")


def restore_backup(payload: dict, resource_id: str) -> dict:
    target_type = payload["target_type"]
    backup_ref = payload["backup_ref"]
    destination_volume = payload.get("volume_id") or payload.get("destination_volume_id")
    if not destination_volume:
        raise StorageOperationError("restore_backup requires the destination volume_id in the payload.")

    # Unlike the backup archive (always qcow2), the *destination* is
    # whatever the disk's storage pool actually is -- writing qcow2
    # container format onto a raw LVM/ZFS block device would corrupt it,
    # since nothing downstream would interpret those bytes as qcow2 (the
    # domain XML's driver type would say "raw"). Convert to whichever
    # format the destination disk actually needs.
    destination_format = payload.get("format", "qcow2")

    if target_type in _FILE_BASED_TARGETS:
        if not os.path.exists(backup_ref):
            raise StorageOperationError(f"Backup artifact not found: {backup_ref}")
        run(["qemu-img", "convert", "-O", destination_format, backup_ref, destination_volume])
        return {}

    if target_type in _S3_COMPATIBLE_TARGETS:
        config = payload["target"]
        client = _s3_client(config)
        with tempfile.TemporaryDirectory(prefix="nodepilot-restore-") as tmpdir:
            local_path = os.path.join(tmpdir, "backup.qcow2")
            client.download_file(config["bucket"], backup_ref, local_path)  # streamed, not loaded into memory
            run(["qemu-img", "convert", "-O", destination_format, local_path, destination_volume])
        return {}

    raise NotImplementedError(f"Backup target type {target_type!r} is not supported by this agent version.")
