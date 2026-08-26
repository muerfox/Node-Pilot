"""
The Agent Protocol (section 52): a closed set of explicitly typed
operations exchanged between the controller and a NodePilot Agent. There
is deliberately no "execute shell command" operation and never will be --
every privileged action the agent can perform has a dedicated, validated
message type here.

Wire format:

    request  {"request_id": "...", "operation": "VM_START", "resource_id": "...", "payload": {...}}
    response {"request_id": "...", "success": true, "data": {...}, "error": null}
"""
from __future__ import annotations

import dataclasses
import uuid
from enum import Enum
from typing import Any


class OperationType(str, Enum):
    # Host introspection
    GET_HOST_INFO = "GET_HOST_INFO"
    GET_DOMAIN_INFO = "GET_DOMAIN_INFO"

    # VM lifecycle
    CREATE_VM = "CREATE_VM"
    DELETE_VM = "DELETE_VM"
    START_VM = "START_VM"
    STOP_VM = "STOP_VM"
    SHUTDOWN_VM = "SHUTDOWN_VM"
    REBOOT_VM = "REBOOT_VM"
    RESET_VM = "RESET_VM"
    PAUSE_VM = "PAUSE_VM"
    RESUME_VM = "RESUME_VM"
    MIGRATE_VM = "MIGRATE_VM"

    # Disks
    CREATE_DISK = "CREATE_DISK"
    DELETE_DISK = "DELETE_DISK"
    RESIZE_DISK = "RESIZE_DISK"
    ATTACH_DISK = "ATTACH_DISK"
    DETACH_DISK = "DETACH_DISK"
    CLONE_DISK = "CLONE_DISK"

    # ISO / media
    ATTACH_ISO = "ATTACH_ISO"
    DETACH_ISO = "DETACH_ISO"

    # Networking
    CREATE_NETWORK = "CREATE_NETWORK"
    DELETE_NETWORK = "DELETE_NETWORK"
    ATTACH_NIC = "ATTACH_NIC"
    DETACH_NIC = "DETACH_NIC"

    # Snapshots
    CREATE_SNAPSHOT = "CREATE_SNAPSHOT"
    DELETE_SNAPSHOT = "DELETE_SNAPSHOT"
    ROLLBACK_SNAPSHOT = "ROLLBACK_SNAPSHOT"

    # Storage pools
    CREATE_STORAGE_POOL = "CREATE_STORAGE_POOL"
    DELETE_STORAGE_POOL = "DELETE_STORAGE_POOL"
    GET_STORAGE_POOL_INFO = "GET_STORAGE_POOL_INFO"

    # Cloud-init
    GENERATE_CLOUD_INIT = "GENERATE_CLOUD_INIT"

    # Console
    OPEN_CONSOLE = "OPEN_CONSOLE"

    # Backups
    CREATE_BACKUP = "CREATE_BACKUP"
    RESTORE_BACKUP = "RESTORE_BACKUP"


# Operations that mutate hypervisor state and therefore must be covered by
# a distributed lock + audit log entry at the call site (section 20 / 30).
DESTRUCTIVE_OPERATIONS = {
    OperationType.DELETE_VM,
    OperationType.DELETE_DISK,
    OperationType.DELETE_NETWORK,
    OperationType.DELETE_SNAPSHOT,
    OperationType.DELETE_STORAGE_POOL,
    OperationType.ROLLBACK_SNAPSHOT,
    OperationType.STOP_VM,
    OperationType.RESET_VM,
}


@dataclasses.dataclass
class AgentRequest:
    operation: OperationType
    resource_id: str
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)
    request_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)

    def to_wire(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "operation": self.operation.value if isinstance(self.operation, OperationType) else self.operation,
            "resource_id": self.resource_id,
            "payload": self.payload,
        }


@dataclasses.dataclass
class AgentResponse:
    request_id: str
    success: bool
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str | None = None

    @classmethod
    def from_wire(cls, message: dict[str, Any]) -> "AgentResponse":
        return cls(
            request_id=message["request_id"],
            success=bool(message.get("success")),
            data=message.get("data") or {},
            error=message.get("error"),
        )
