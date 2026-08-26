"""
Reconciliation subsystem (section 51). The controller's database is a
*desired-state* record; it can drift from what libvirt actually reports on
each node (agent restarts, manual virsh use, crashes, etc). This module
never silently corrects that drift -- it only detects it and emits an
Event so an operator (or, later, an explicit reconciliation job) can act.
"""
from __future__ import annotations

import logging

from apps.nodes.models import Node, NodeStatus

logger = logging.getLogger("nodepilot.reconciliation")


def reconcile_node(node: Node) -> bool:
    """Compares the VM count NodePilot believes it manages on this node
    against the count the agent last reported in its heartbeat. A mismatch
    means either an out-of-band VM exists on the hypervisor, or the
    database has a VM record for something that no longer exists there.
    Returns True if a mismatch event was emitted."""
    if node.effective_status() != NodeStatus.ONLINE:
        return False

    from apps.virtual_machines.models import VirtualMachine, VMStatus

    db_count = VirtualMachine.objects.filter(node=node).exclude(status=VMStatus.DELETING).count()
    if db_count == node.reported_vm_count:
        return False

    from apps.events.services import emit_event

    emit_event(
        type="RECONCILIATION_MISMATCH",
        severity="WARNING",
        resource_type="Node",
        resource_id=str(node.uuid),
        organization=node.organization,
        metadata={
            "database_vm_count": db_count,
            "agent_reported_vm_count": node.reported_vm_count,
        },
    )
    logger.warning("Reconciliation mismatch on node %s: db=%s agent=%s", node.uuid, db_count, node.reported_vm_count)
    return True


def reconcile_all() -> int:
    mismatches = 0
    for node in Node.objects.all():
        if reconcile_node(node):
            mismatches += 1
    return mismatches
