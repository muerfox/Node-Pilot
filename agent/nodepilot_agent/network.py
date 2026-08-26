"""
Linux bridge/VLAN management (section 22). All mutations go through the
`ip` command with argument lists (never a shell string), matching the
same "no shell=True on user-controlled data" rule as storage.py.
"""
from __future__ import annotations

import re
import subprocess

_SAFE_IFACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,14}$")  # IFNAMSIZ is 16 bytes incl. NUL


class NetworkOperationError(RuntimeError):
    pass


def _validate_iface(name: str) -> str:
    if not _SAFE_IFACE.match(name):
        raise NetworkOperationError(f"Unsafe/invalid interface name: {name!r}")
    return name


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)
    except subprocess.CalledProcessError as exc:
        raise NetworkOperationError(f"{' '.join(args)} failed: {exc.stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise NetworkOperationError(f"{' '.join(args)} timed out") from exc


def bridge_exists(name: str) -> bool:
    name = _validate_iface(name)
    result = _run(["ip", "-json", "link", "show", "type", "bridge", name], check=False)
    return result.returncode == 0 and result.stdout.strip() not in ("", "[]")


def create_bridge(name: str) -> None:
    name = _validate_iface(name)
    if bridge_exists(name):
        return
    _run(["ip", "link", "add", "name", name, "type", "bridge"])
    _run(["ip", "link", "set", name, "up"])


def delete_bridge(name: str) -> None:
    name = _validate_iface(name)
    _run(["ip", "link", "set", name, "down"], check=False)
    _run(["ip", "link", "delete", name, "type", "bridge"])


def vlan_interface_name(parent: str, vlan_id: int) -> str:
    return _validate_iface(f"{parent}.{vlan_id}")


def create_vlan_interface(parent: str, vlan_id: int) -> str:
    parent = _validate_iface(parent)
    if not (1 <= vlan_id <= 4094):
        raise NetworkOperationError(f"VLAN id out of range: {vlan_id}")
    iface = vlan_interface_name(parent, vlan_id)
    _run(["ip", "link", "add", "link", parent, "name", iface, "type", "vlan", "id", str(vlan_id)])
    _run(["ip", "link", "set", iface, "up"])
    return iface


def delete_vlan_interface(parent: str, vlan_id: int) -> None:
    iface = vlan_interface_name(parent, vlan_id)
    _run(["ip", "link", "set", iface, "down"], check=False)
    _run(["ip", "link", "delete", iface], check=False)


def attach_to_bridge(iface: str, bridge: str) -> None:
    iface, bridge = _validate_iface(iface), _validate_iface(bridge)
    _run(["ip", "link", "set", iface, "master", bridge])
