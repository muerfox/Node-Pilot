"""
Host and VM metrics collection. Every number here comes from psutil or
libvirt -- never fabricated (rule 2: "do not return fake VM metrics").
If a VM's stats can't be read (e.g. it's not running), the caller gets an
empty dict, not a made-up zero.
"""
from __future__ import annotations

import psutil

from nodepilot_agent.libvirt_client import LibvirtClient, LibvirtOperationError


def collect_host_metrics() -> dict:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load1, load5, load15 = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0.0, 0.0, 0.0)
    net = psutil.net_io_counters()

    return {
        "cpu": {"percent": psutil.cpu_percent(interval=0.1), "count": psutil.cpu_count()},
        "memory": {"total_mb": memory.total // (1024 * 1024), "available_mb": memory.available // (1024 * 1024)},
        "storage": {"total_gb": disk.total // (1024**3), "available_gb": disk.free // (1024**3)},
        "load": {"load1": load1, "load5": load5, "load15": load15},
        "network": {"rx_bytes": net.bytes_recv, "tx_bytes": net.bytes_sent},
    }


def collect_vm_metrics(client: LibvirtClient, domain_uuid: str) -> dict:
    try:
        stats = client.domain_stats(domain_uuid)
    except LibvirtOperationError:
        return {}
    if not stats:
        return {}

    memory = stats.get("memory", {})
    return {
        "memory_used_mb": memory.get("rss", 0) // 1024 if memory.get("rss") else None,
        "raw_cpu_stats": stats.get("cpu"),
    }
