"""
Per-VM metrics loop (section 28). Runs alongside the host heartbeat, on
its own asyncio task, and pushes real samples to the controller's
`/api/v1/agent/vm-metrics/` -- never fabricated (rule 2), and simply
skipped for a domain until a second sample is available, since CPU
utilization is inherently a delta between two `cpu_time` readings.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from nodepilot_agent.config import AgentConfig
from nodepilot_agent.libvirt_client import LIBVIRT_AVAILABLE, LibvirtClient

logger = logging.getLogger("nodepilot_agent.vm_metrics")


class _DomainCpuTracker:
    """Tracks the last (cpu_time_ns, wall_clock) reading per domain so
    utilization can be computed as a delta -- a single libvirt sample is
    just a cumulative counter, not a percentage."""

    def __init__(self):
        self._last: dict[str, tuple[int, float]] = {}

    def sample(self, domain_uuid: str, cpu_time_ns: int, nr_virt_cpu: int) -> float | None:
        now = time.monotonic()
        previous = self._last.get(domain_uuid)
        self._last[domain_uuid] = (cpu_time_ns, now)

        if previous is None:
            return None  # First sighting of this domain -- no delta yet.

        prev_cpu_time_ns, prev_time = previous
        delta_wall = now - prev_time
        if delta_wall <= 0:
            return None

        delta_cpu = cpu_time_ns - prev_cpu_time_ns
        if delta_cpu < 0:
            return None  # Domain was likely reset/migrated; counter went backwards.

        # Normalized 0-100% average utilization across the VM's own
        # allocated vCPUs (the same convention virt-top/top use), not
        # against the host's total core count.
        percent = (delta_cpu / (delta_wall * 1_000_000_000 * max(nr_virt_cpu, 1))) * 100
        return round(min(percent, 100.0), 1)

    def forget_missing(self, active_domain_uuids: set[str]) -> None:
        for domain_uuid in list(self._last):
            if domain_uuid not in active_domain_uuids:
                del self._last[domain_uuid]


def _collect_samples(libvirt_client: LibvirtClient, tracker: _DomainCpuTracker) -> list[dict]:
    conn = libvirt_client.connect()
    samples = []
    active_uuids = set()

    for dom in conn.listAllDomains():
        if not dom.isActive():
            continue
        domain_uuid = dom.UUIDString()
        active_uuids.add(domain_uuid)

        try:
            _state, _max_mem_kb, mem_kb, nr_virt_cpu, cpu_time_ns = dom.info()
        except Exception:  # pragma: no cover - a domain can vanish between listing and info()
            logger.exception("Failed to read info() for domain %s", domain_uuid)
            continue

        cpu_percent = tracker.sample(domain_uuid, cpu_time_ns, nr_virt_cpu)

        memory_used_mb = None
        try:
            mem_stats = dom.memoryStats()
            if mem_stats.get("rss"):
                memory_used_mb = mem_stats["rss"] // 1024
        except Exception:  # pragma: no cover - memoryStats needs a guest agent/balloon driver in some configs
            pass
        if memory_used_mb is None and mem_kb:
            memory_used_mb = mem_kb // 1024

        samples.append({"domain_uuid": domain_uuid, "cpu_percent": cpu_percent, "memory_used_mb": memory_used_mb})

    tracker.forget_missing(active_uuids)
    return samples


async def vm_metrics_loop(config: AgentConfig, libvirt_client: LibvirtClient, stop_event: asyncio.Event) -> None:
    if not LIBVIRT_AVAILABLE:
        logger.info("libvirt-python not installed; per-VM metrics collection is disabled on this agent.")
        return

    tracker = _DomainCpuTracker()
    headers = {"Authorization": f"Agent {config.agent_token}"}
    url = f"{config.controller_url.rstrip('/')}/api/v1/agent/vm-metrics/"

    async with httpx.AsyncClient(verify=config.tls_verify, timeout=10.0) as client:
        while not stop_event.is_set():
            try:
                loop = asyncio.get_event_loop()
                samples = await loop.run_in_executor(None, _collect_samples, libvirt_client, tracker)
                # Drop first-sighting entries (cpu_percent is None) rather
                # than sending a sample the controller would just discard.
                samples = [s for s in samples if s["cpu_percent"] is not None or s["memory_used_mb"] is not None]
                if samples:
                    response = await client.post(url, json={"samples": samples}, headers=headers)
                    if response.status_code >= 400:
                        logger.warning("VM metrics push rejected (%s): %s", response.status_code, response.text[:500])
            except Exception:
                logger.exception("VM metrics collection failed")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=config.heartbeat_interval_seconds)
            except asyncio.TimeoutError:
                pass
