"""
The NodePilot Agent Protocol (section 52). This mirrors
backend/apps/nodes/protocol.py exactly -- it's the wire contract, not
shared implementation, so the two projects deliberately don't share code
(the controller and agent are independently deployed/versioned).

There is no "execute shell command" operation here, and there never will
be (section 4): every privileged action is one of these explicit,
validated message types.
"""
from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any


class OperationType(str, Enum):
    GET_HOST_INFO = "GET_HOST_INFO"
    GET_DOMAIN_INFO = "GET_DOMAIN_INFO"

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

    CREATE_DISK = "CREATE_DISK"
    DELETE_DISK = "DELETE_DISK"
    RESIZE_DISK = "RESIZE_DISK"
    ATTACH_DISK = "ATTACH_DISK"
    DETACH_DISK = "DETACH_DISK"
    CLONE_DISK = "CLONE_DISK"

    ATTACH_ISO = "ATTACH_ISO"
    DETACH_ISO = "DETACH_ISO"

    CREATE_NETWORK = "CREATE_NETWORK"
    DELETE_NETWORK = "DELETE_NETWORK"
    ATTACH_NIC = "ATTACH_NIC"
    DETACH_NIC = "DETACH_NIC"

    CREATE_SNAPSHOT = "CREATE_SNAPSHOT"
    DELETE_SNAPSHOT = "DELETE_SNAPSHOT"
    ROLLBACK_SNAPSHOT = "ROLLBACK_SNAPSHOT"

    CREATE_STORAGE_POOL = "CREATE_STORAGE_POOL"
    DELETE_STORAGE_POOL = "DELETE_STORAGE_POOL"
    GET_STORAGE_POOL_INFO = "GET_STORAGE_POOL_INFO"

    GENERATE_CLOUD_INIT = "GENERATE_CLOUD_INIT"
    OPEN_CONSOLE = "OPEN_CONSOLE"

    CREATE_BACKUP = "CREATE_BACKUP"
    RESTORE_BACKUP = "RESTORE_BACKUP"


@dataclasses.dataclass
class AgentRequest:
    request_id: str
    operation: OperationType
    resource_id: str
    payload: dict[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_wire(cls, message: dict[str, Any]) -> "AgentRequest":
        return cls(
            request_id=message["request_id"],
            operation=OperationType(message["operation"]),
            resource_id=message.get("resource_id", ""),
            payload=message.get("payload") or {},
        )


@dataclasses.dataclass
class AgentResponse:
    request_id: str
    success: bool
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    error: str | None = None

    def to_wire(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "success": self.success, "data": self.data, "error": self.error}

    @classmethod
    def ok(cls, request_id: str, data: dict[str, Any] | None = None) -> "AgentResponse":
        return cls(request_id=request_id, success=True, data=data or {})

    @classmethod
    def fail(cls, request_id: str, error: str) -> "AgentResponse":
        return cls(request_id=request_id, success=False, error=error)
