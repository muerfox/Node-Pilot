from __future__ import annotations

import json
import logging
import time
import uuid

from django.utils.deprecation import MiddlewareMixin

from apps.common.idempotency import IDEMPOTENT_METHODS, get_cached_response, store_response
from apps.common.logging_utils import organization_id_var, request_id_var, user_id_var

logger = logging.getLogger("nodepilot.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(MiddlewareMixin):
    """
    Assigns a request_id to every request, exposes it on the response, and
    emits one structured access log line per request carrying request_id /
    user_id / organization_id / operation / duration / result.
    """

    def process_request(self, request):
        request.request_id = request.META.get(f"HTTP_{REQUEST_ID_HEADER.upper().replace('-', '_')}") or uuid.uuid4().hex
        request_id_var.set(request.request_id)
        user_id_var.set(None)
        organization_id_var.set(None)
        request._nodepilot_start = time.monotonic()

    def process_response(self, request, response):
        response[REQUEST_ID_HEADER] = getattr(request, "request_id", "")
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            user_id_var.set(str(getattr(user, "uuid", user.pk)))
        duration = time.monotonic() - getattr(request, "_nodepilot_start", time.monotonic())
        logger.info(
            "%s %s -> %s",
            request.method,
            request.path,
            response.status_code,
            extra={
                "context": {
                    "operation": f"{request.method} {request.path}",
                    "duration": round(duration, 4),
                    "result": "success" if response.status_code < 400 else "error",
                    "status_code": response.status_code,
                }
            },
        )
        return response


class IdempotencyMiddleware(MiddlewareMixin):
    """
    Generic Idempotency-Key support (section 33). If a client retries a
    provisioning request with the same Idempotency-Key, the cached response
    is replayed instead of re-executing the request. Scoped per
    (authenticated principal, method, path, key) with a bounded TTL.

    This is a best-effort cache for read-after-retry safety; the
    authoritative guarantee for VM creation additionally comes from a
    unique DB constraint (see apps.virtual_machines).
    """

    def process_request(self, request):
        if request.method not in IDEMPOTENT_METHODS:
            return None
        key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not key:
            return None
        principal = _principal_id(request)
        cached = get_cached_response(principal, request.method, request.path, key)
        if cached is None:
            request._idempotency_key = key
            request._idempotency_principal = principal
            return None
        from django.http import JsonResponse

        response = JsonResponse(cached["body"], status=cached["status"])
        response["Idempotent-Replay"] = "true"
        return response

    def process_response(self, request, response):
        key = getattr(request, "_idempotency_key", None)
        if not key or response.status_code >= 500:
            return response
        if 200 <= response.status_code < 300 and hasattr(response, "content"):
            try:
                body = json.loads(response.content or b"{}")
            except ValueError:
                return response
            store_response(request._idempotency_principal, request.method, request.path, key, response.status_code, body)
        return response


def _principal_id(request) -> str:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return f"user:{user.pk}"
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    return f"anon:{hash(auth_header)}"
