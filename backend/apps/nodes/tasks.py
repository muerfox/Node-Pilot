from celery import shared_task

from apps.nodes.models import Node
from apps.nodes.services import mark_offline_if_stale


@shared_task(name="nodes.sweep_offline_nodes")
def sweep_offline_nodes() -> int:
    """Runs on a short Celery Beat interval; detects nodes whose heartbeat
    has gone stale and emits NODE_OFFLINE (state itself is always computed
    live via Node.effective_status(), never trusted from a stored field)."""
    changed = 0
    for node in Node.objects.exclude(admin_state__in=["MAINTENANCE", "DISABLED"]):
        if mark_offline_if_stale(node):
            changed += 1
    return changed


@shared_task(name="nodes.reconcile_nodes")
def reconcile_nodes() -> int:
    from apps.nodes.reconciliation import reconcile_all

    return reconcile_all()
