"""
Central place to obtain Redis connections. Redis is used only for the
Celery broker, distributed locks, idempotency caching, short-lived metrics,
and websocket/event fan-out -- never as the system of record.
"""
from __future__ import annotations

from functools import lru_cache

import redis
from django.conf import settings


@lru_cache(maxsize=None)
def get_redis(url: str | None = None) -> "redis.Redis":
    return redis.Redis.from_url(url or settings.REDIS_URL, decode_responses=True)
