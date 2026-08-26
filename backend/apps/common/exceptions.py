"""
Standard error envelope for the whole API:

    {"error": {"code": "VM_ALREADY_RUNNING", "message": "...", "details": {}}}

Domain code should raise NodePilotAPIException subclasses (or the generic
class with an explicit `code`) instead of returning ad-hoc error bodies.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class NodePilotAPIException(APIException):
    code_name = "ERROR"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str | None = None, details: dict | None = None, code_name: str | None = None):
        self.code_name = code_name or self.code_name
        self.details = details or {}
        super().__init__(detail=message or self.default_detail)


class ValidationFailed(NodePilotAPIException):
    code_name = "VALIDATION_FAILED"
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The request could not be validated."


class ResourceLocked(NodePilotAPIException):
    code_name = "RESOURCE_LOCKED"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource is currently locked by another operation."


class QuotaExceeded(NodePilotAPIException):
    code_name = "QUOTA_EXCEEDED"
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "This operation would exceed the organization's resource quota."


class PermissionDeniedError(NodePilotAPIException):
    code_name = "PERMISSION_DENIED"
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to perform this action."


class AgentUnavailable(NodePilotAPIException):
    code_name = "AGENT_UNAVAILABLE"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The node agent is not currently connected."


class AgentOperationFailed(NodePilotAPIException):
    code_name = "AGENT_OPERATION_FAILED"
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The node agent reported an error executing the operation."


class AgentVersionUnsupported(NodePilotAPIException):
    code_name = "AGENT_VERSION_UNSUPPORTED"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The agent's protocol version is not compatible with this controller."


class InvalidStateTransition(NodePilotAPIException):
    code_name = "INVALID_STATE_TRANSITION"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The requested operation is not valid for the resource's current state."


class StorageCapabilityUnsupported(NodePilotAPIException):
    code_name = "STORAGE_CAPABILITY_UNSUPPORTED"
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The storage backend does not support this operation."


def nodepilot_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, NodePilotAPIException):
        code = exc.code_name
        details = exc.details
    else:
        code = getattr(exc, "default_code", exc.__class__.__name__.upper())
        raw = response.data
        details = raw if isinstance(raw, dict) and "detail" not in raw else {}

    message = response.data.get("detail") if isinstance(response.data, dict) else str(response.data)
    if message is None:
        message = str(exc)

    return Response({"error": {"code": str(code), "message": str(message), "details": details}}, status=response.status_code)
