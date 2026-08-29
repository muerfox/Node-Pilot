from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import AgentVersionUnsupported
from apps.nodes.models import Agent, Node, NodeStatus

logger = logging.getLogger("nodepilot.nodes")


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def check_agent_version_compatible(agent_version: str) -> None:
    minimum = settings.NODEPILOT["MIN_SUPPORTED_AGENT_VERSION"]
    if _version_tuple(agent_version) < _version_tuple(minimum):
        raise AgentVersionUnsupported(
            f"Agent version {agent_version} is older than the minimum supported version {minimum}.",
            details={"agent_version": agent_version, "minimum_supported": minimum},
        )


@transaction.atomic
def record_heartbeat(agent: Agent, payload: dict) -> Node:
    """
    Ingests a periodic agent heartbeat (section 53). Only non-destructive
    state (metrics, last_seen, reported inventory) is written here --
    reconciliation of desired-vs-actual VM state is a separate concern
    (apps.nodes.reconciliation) that only ever emits events, never
    silently mutates resources.
    """
    check_agent_version_compatible(payload.get("agent_version", ""))

    node = Node.objects.select_for_update().get(pk=agent.node_id)
    was_online = node.effective_status() == NodeStatus.ONLINE

    cpu = payload.get("cpu", {})
    memory = payload.get("memory", {})
    storage = payload.get("storage", {})

    node.agent_version = payload.get("agent_version", node.agent_version)
    node.kernel = payload.get("kernel", node.kernel)
    node.architecture = payload.get("architecture", node.architecture)
    node.cpu_model = cpu.get("model", node.cpu_model)
    node.cpu_threads = cpu.get("threads", node.cpu_threads)
    node.cpu_cores = cpu.get("cores", node.cpu_cores)
    node.cpu_sockets = cpu.get("sockets", node.cpu_sockets)
    node.memory_total_mb = memory.get("total_mb", node.memory_total_mb)
    node.memory_available_mb = memory.get("available_mb", node.memory_available_mb)
    node.storage_total_gb = storage.get("total_gb", node.storage_total_gb)
    node.storage_available_gb = storage.get("available_gb", node.storage_available_gb)
    node.reported_vm_count = payload.get("vms", node.reported_vm_count)
    node.last_seen = timezone.now()
    node.save()

    agent.last_heartbeat_at = timezone.now()
    agent.protocol_version = payload.get("protocol_version", agent.protocol_version)
    agent.save(update_fields=["last_heartbeat_at", "protocol_version"])

    # Record the sample in the short-term metrics store (Redis-backed --
    # see apps.metrics), never accumulated indefinitely in PostgreSQL.
    try:
        from apps.metrics.store import record_node_sample

        record_node_sample(node, cpu=cpu, memory=memory, storage=storage)
    except Exception:  # pragma: no cover - metrics must never break heartbeats.
        logger.exception("Failed to record metrics sample for node %s", node.uuid)

    if not was_online:
        from apps.events.services import emit_event

        emit_event(
            type="NODE_ONLINE",
            severity="INFO",
            resource_type="Node",
            resource_id=str(node.uuid),
            organization=node.organization,
            metadata={"hostname": node.hostname},
        )

    from apps.nodes.consumers import broadcast_node_status

    broadcast_node_status(node)
    return node


def mark_offline_if_stale(node: Node) -> bool:
    """Called by the periodic sweep task; emits NODE_OFFLINE exactly once
    per online->offline transition rather than on every poll."""
    if node.effective_status() != NodeStatus.OFFLINE:
        return False
    from apps.events.models import Event
    from apps.events.services import emit_event

    already_notified = Event.objects.filter(
        type="NODE_OFFLINE", resource_type="Node", resource_id=str(node.uuid), created_at__gte=node.last_seen or node.created_at
    ).exists()
    if already_notified:
        return False

    emit_event(
        type="NODE_OFFLINE",
        severity="CRITICAL",
        resource_type="Node",
        resource_id=str(node.uuid),
        organization=node.organization,
        metadata={"hostname": node.hostname, "last_seen": node.last_seen.isoformat() if node.last_seen else None},
    )
    from apps.nodes.consumers import broadcast_node_status

    broadcast_node_status(node)
    return True


def record_vm_metrics_batch(agent: Agent, samples: list[dict]) -> int:
    """
    Ingests a batch of per-VM samples pushed by the agent's metrics loop
    (nodepilot_agent.vm_metrics). Each sample is keyed by the libvirt
    `domain_uuid` -- the only identifier the agent actually has -- which
    is resolved to a VirtualMachine scoped to this agent's own node, so
    one compromised/misbehaving agent can never write metrics for a VM it
    doesn't own. Samples for a domain_uuid NodePilot doesn't recognize on
    this node are silently skipped (e.g. a stale sample, or reconciliation
    hasn't caught up yet) rather than raising -- a metrics ingest
    endpoint should never fail hard because inventory briefly drifted.
    """
    from apps.metrics.store import record_vm_sample
    from apps.virtual_machines.models import VirtualMachine

    domain_uuids = [s["domain_uuid"] for s in samples]
    vms_by_domain = {
        str(vm.domain_uuid): vm
        for vm in VirtualMachine.objects.filter(node=agent.node, domain_uuid__in=domain_uuids)
    }

    recorded = 0
    for sample in samples:
        vm = vms_by_domain.get(str(sample["domain_uuid"]))
        if vm is None:
            continue
        record_vm_sample(
            vm,
            cpu_percent=sample.get("cpu_percent"),
            memory_used_mb=sample.get("memory_used_mb"),
            disk_read_bytes=None,
            disk_write_bytes=None,
            net_rx_bytes=None,
            net_tx_bytes=None,
        )
        recorded += 1
    return recorded
