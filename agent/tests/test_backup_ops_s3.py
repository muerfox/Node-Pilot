"""
Real S3 upload/download flow for backup create/restore, against a mocked
AWS backend (moto) rather than talking to real S3/MinIO/Ceph -- covers
what MinIO and Ceph RGW share with real S3 (they all speak the same
API), and proves the checksum/format handling is correct end to end.
`qemu-img` itself is stubbed out (not installed in this environment; see
test_storage_directory.py for the same pattern) by making the stub copy
bytes through, so the S3 upload/download plumbing is exercised for real.
"""
from __future__ import annotations

import hashlib
import os

import boto3
import pytest
from moto import mock_aws

from nodepilot_agent.operations import backup_ops


def _fake_qemu_img_convert(args, **kwargs):
    """Stands in for `run(["qemu-img", "convert", "-O", fmt, src, dst])`
    -- copies bytes through so the rest of the pipeline (checksum, S3
    upload/download, final restore) is exercised against real data."""
    assert args[0] == "qemu-img"
    src, dst = args[-2], args[-1]
    with open(src, "rb") as fh:
        data = fh.read()
    with open(dst, "wb") as fh:
        fh.write(data)


@pytest.fixture
def source_disk(tmp_path):
    path = tmp_path / "source-disk.img"
    path.write_bytes(b"fake qcow2 disk contents" * 1000)
    return str(path)


@mock_aws
def test_create_backup_uploads_to_s3_and_returns_a_matching_checksum(monkeypatch, source_disk):
    monkeypatch.setattr(backup_ops, "run", _fake_qemu_img_convert)
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="nodepilot-backups")

    payload = {
        "target_type": "S3",
        "backup_uuid": "11111111-1111-1111-1111-111111111111",
        "volume_id": source_disk,
        "target": {"bucket": "nodepilot-backups", "prefix": "vm-backups", "region": "us-east-1"},
    }

    result = backup_ops.create_backup(payload, resource_id="vm-1")

    assert result["backup_ref"] == "vm-backups/11111111-1111-1111-1111-111111111111.qcow2"
    expected_checksum = hashlib.sha256(open(source_disk, "rb").read()).hexdigest()
    assert result["checksum"] == expected_checksum
    assert result["size_bytes"] == os.path.getsize(source_disk)

    # The object is really there, with server-side encryption applied.
    obj = boto3.client("s3", region_name="us-east-1").get_object(Bucket="nodepilot-backups", Key=result["backup_ref"])
    assert obj["Body"].read() == open(source_disk, "rb").read()
    assert obj["ServerSideEncryption"] == "AES256"


@mock_aws
def test_restore_backup_downloads_from_s3_and_writes_the_destination(monkeypatch, source_disk, tmp_path):
    monkeypatch.setattr(backup_ops, "run", _fake_qemu_img_convert)
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="nodepilot-backups")
    key = "vm-backups/backup.qcow2"
    client.upload_file(source_disk, "nodepilot-backups", key)

    destination = str(tmp_path / "restored-disk.img")
    payload = {
        "target_type": "S3",
        "backup_ref": key,
        "volume_id": destination,
        "format": "raw",
        "target": {"bucket": "nodepilot-backups", "region": "us-east-1"},
    }

    backup_ops.restore_backup(payload, resource_id="vm-1")

    assert open(destination, "rb").read() == open(source_disk, "rb").read()


def test_create_backup_raises_a_clear_error_for_a_target_type_with_no_backend(source_disk):
    payload = {"target_type": "NOT_A_REAL_TYPE", "backup_uuid": "x", "volume_id": source_disk, "target": {}}
    with pytest.raises(NotImplementedError):
        backup_ops.create_backup(payload, resource_id="vm-1")
