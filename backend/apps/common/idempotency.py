from __future__ import annotations

import hashlib
import json

from django.conf import settings

from apps.common.redis_client import get_redis

IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}


def _cache_key(principal: str, method: str, path: str, key: str) -> str:
    digest = hashlib.sha256(f"{principal}:{method}:{path}:{key}".encode()).hexdigest()
    return f"nodepilot:idempotency:{digest}"


def get_cached_response(principal: str, method: str, path: str, key: str) -> dict | None:
    raw = get_redis().get(_cache_key(principal, method, path, key))
    if raw is None:
        return None
    return json.loads(raw)


def store_response(principal: str, method: str, path: str, key: str, status: int, body: dict) -> None:
    ttl = settings.NODEPILOT["IDEMPOTENCY_KEY_TTL_SECONDS"]
    get_redis().set(_cache_key(principal, method, path, key), json.dumps({"status": status, "body": body}), ex=ttl)
