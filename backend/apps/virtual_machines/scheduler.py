"""
Pluggable node scheduler (section 42): when a VM is created without an
explicit node, pick the best candidate from the organization's ONLINE,
schedulable nodes based on available capacity.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from apps.common.exceptions import NodePilotAPIException


class NoSchedulableNode(NodePilotAPIException):
    code_name = "NO_SCHEDULABLE_NODE"
    status_code = 409
    default_detail = "No online node has enough free capacity for this VM."


@dataclass
class SchedulingRequest:
    organization_id: int
    cpu_count: int
    memory_mb: int
    disk_gb: int
    preferred_node_id: int | None = None


@dataclass
class NodeScore:
    node: "object"
    score: float


class Scheduler(abc.ABC):
    @abc.abstractmethod
    def select_node(self, request: SchedulingRequest):
        ...


class CapacityWeightedScheduler(Scheduler):
    """
    Default scheduler: scores each schedulable node by remaining
    CPU/memory/storage headroom after the candidate VM is hypothetically
    placed, favoring nodes with the most balanced spare capacity. Nodes in
    maintenance, disabled, or not currently ONLINE are excluded entirely.
    """

    CPU_OVERCOMMIT_RATIO = 4  # vCPUs may exceed physical threads by this factor.

    def select_node(self, request: SchedulingRequest):
        from apps.nodes.models import Node, NodeStatus

        candidates = Node.objects.filter(organization_id=request.organization_id)
        scored: list[NodeScore] = []
        for node in candidates:
            if node.effective_status() != NodeStatus.ONLINE or not node.is_schedulable():
                continue

            max_vcpu = max(node.cpu_threads, 1) * self.CPU_OVERCOMMIT_RATIO
            used_vcpu = _used_vcpu(node)
            free_vcpu = max_vcpu - used_vcpu
            if free_vcpu < request.cpu_count:
                continue

            free_memory_mb = node.memory_available_mb
            if free_memory_mb < request.memory_mb:
                continue

            free_storage_gb = node.storage_available_gb
            if free_storage_gb < request.disk_gb:
                continue

            cpu_headroom = (free_vcpu - request.cpu_count) / max_vcpu
            mem_headroom = (free_memory_mb - request.memory_mb) / max(node.memory_total_mb, 1)
            storage_headroom = (free_storage_gb - request.disk_gb) / max(node.storage_total_gb, 1)
            score = round(100 * (0.4 * cpu_headroom + 0.4 * mem_headroom + 0.2 * storage_headroom), 2)
            scored.append(NodeScore(node=node, score=score))

        if not scored:
            raise NoSchedulableNode()

        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[0].node


def _used_vcpu(node) -> int:
    from apps.virtual_machines.models import VirtualMachine, VMStatus

    return sum(
        VirtualMachine.objects.filter(node=node, status=VMStatus.RUNNING).values_list("cpu_count", flat=True)
    )


def get_scheduler() -> Scheduler:
    return CapacityWeightedScheduler()
