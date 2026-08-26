"""
Short-term metrics store (section 28). Deliberately NOT a Django model --
writing every heartbeat/metrics sample to PostgreSQL indefinitely does not
scale. Samples live in Redis sorted sets (score = unix timestamp), capped
by both a point count and a retention window, and simply expire.

`MetricsStore` is an abstract interface so a future Prometheus-backed
implementation (remote_write, or the controller acting as an exporter)
can be swapped in without touching call sites in apps.nodes/apps.
virtual_machines.
"""
from __future__ import annotations

import abc
import json
import time

from django.conf import settings

from apps.common.redis_client import get_redis

NODE_KEY_PREFIX = "nodepilot:metrics:node:"
VM_KEY_PREFIX = "nodepilot:metrics:vm:"


class MetricsStore(abc.ABC):
    @abc.abstractmethod
    def record(self, key: str, sample: dict) -> None: ...

    @abc.abstractmethod
    def query(self, key: str, since_seconds: int | None = None) -> list[dict]: ...


class RedisMetricsStore(MetricsStore):
    def record(self, key: str, sample: dict) -> None:
        redis = get_redis()
        retention = settings.NODEPILOT["METRICS_RETENTION_SECONDS"]
        max_points = settings.NODEPILOT["METRICS_SAMPLE_MAX_POINTS"]
        now = time.time()

        sample = {"ts": now, **sample}
        redis.zadd(key, {json.dumps(sample): now})
        redis.zremrangebyscore(key, 0, now - retention)
        redis.zremrangebyrank(key, 0, -(max_points + 1))  # keep only the most recent max_points
        redis.expire(key, retention)

    def query(self, key: str, since_seconds: int | None = None) -> list[dict]:
        redis = get_redis()
        now = time.time()
        min_score = now - since_seconds if since_seconds else "-inf"
        raw = redis.zrangebyscore(key, min_score, now)
        return [json.loads(item) for item in raw]


_store: MetricsStore = RedisMetricsStore()


def get_metrics_store() -> MetricsStore:
    return _store


def record_node_sample(node, *, cpu: dict, memory: dict, storage: dict) -> None:
    get_metrics_store().record(
        f"{NODE_KEY_PREFIX}{node.uuid}",
        {
            "cpu_percent": cpu.get("percent"),
            "memory_used_mb": memory.get("total_mb", 0) - memory.get("available_mb", 0) if memory.get("total_mb") else None,
            "memory_total_mb": memory.get("total_mb"),
            "storage_used_gb": storage.get("total_gb", 0) - storage.get("available_gb", 0) if storage.get("total_gb") else None,
        },
    )


def record_vm_sample(vm, *, cpu_percent: float | None, memory_used_mb: int | None, disk_read_bytes: int | None, disk_write_bytes: int | None, net_rx_bytes: int | None, net_tx_bytes: int | None) -> None:
    get_metrics_store().record(
        f"{VM_KEY_PREFIX}{vm.uuid}",
        {
            "cpu_percent": cpu_percent,
            "memory_used_mb": memory_used_mb,
            "disk_read_bytes": disk_read_bytes,
            "disk_write_bytes": disk_write_bytes,
            "net_rx_bytes": net_rx_bytes,
            "net_tx_bytes": net_tx_bytes,
        },
    )


def get_node_samples(node, since_seconds: int | None = None) -> list[dict]:
    return get_metrics_store().query(f"{NODE_KEY_PREFIX}{node.uuid}", since_seconds)


def get_vm_samples(vm, since_seconds: int | None = None) -> list[dict]:
    return get_metrics_store().query(f"{VM_KEY_PREFIX}{vm.uuid}", since_seconds)
