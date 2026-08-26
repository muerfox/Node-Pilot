"""
Generates a cloud-init NoCloud data source ISO (section 17). NodePilot
never stores plaintext passwords unnecessarily -- if a password isn't
explicitly requested, cloud-init is configured for SSH-key auth only, and
any password that *is* supplied is written straight into the transient
user-data file and never logged or echoed back.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


class CloudInitError(RuntimeError):
    pass


def _build_user_data(config: dict) -> str:
    user_data: dict = {"hostname": config.get("hostname", "nodepilot-vm")}

    users = config.get("users")
    if users:
        user_data["users"] = users
    elif config.get("username"):
        entry = {"name": config["username"], "sudo": "ALL=(ALL) NOPASSWD:ALL", "shell": "/bin/bash"}
        if config.get("ssh_keys"):
            entry["ssh_authorized_keys"] = config["ssh_keys"]
        if config.get("password"):
            entry["lock_passwd"] = False
            entry["plain_text_passwd"] = config["password"]
        user_data["users"] = [entry]

    if config.get("packages"):
        user_data["packages"] = config["packages"]
    if config.get("write_files"):
        user_data["write_files"] = config["write_files"]
    if config.get("runcmd"):
        user_data["runcmd"] = config["runcmd"]

    return "#cloud-config\n" + yaml.safe_dump(user_data, sort_keys=False)


def _build_network_config(config: dict) -> str | None:
    network = config.get("network")
    if not network:
        return None
    return yaml.safe_dump({"version": 2, "ethernets": network}, sort_keys=False)


def generate_nocloud_iso(config: dict, output_path: str) -> str:
    """Writes user-data/meta-data(/network-config) and packs them into a
    NoCloud ISO at `output_path` using genisoimage. Returns output_path."""
    tool = shutil.which("genisoimage") or shutil.which("mkisofs") or shutil.which("xorriso")
    if tool is None:
        raise CloudInitError("None of genisoimage/mkisofs/xorriso is installed; cannot build a cloud-init ISO.")

    with tempfile.TemporaryDirectory(prefix="nodepilot-cloudinit-") as tmpdir:
        tmp = Path(tmpdir)
        (tmp / "user-data").write_text(_build_user_data(config))
        (tmp / "meta-data").write_text(
            yaml.safe_dump({"instance-id": config.get("instance_id", config.get("hostname", "nodepilot-vm")), "local-hostname": config.get("hostname", "nodepilot-vm")})
        )
        network_config = _build_network_config(config)
        if network_config:
            (tmp / "network-config").write_text(network_config)

        args = [tool, "-output", output_path, "-volid", "cidata", "-joliet", "-rock", str(tmp / "user-data"), str(tmp / "meta-data")]
        if network_config:
            args.append(str(tmp / "network-config"))

        result = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise CloudInitError(f"Failed to build cloud-init ISO: {result.stderr}")

    return output_path
