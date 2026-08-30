"""
apps.nodes.tasks.sweep_offline_nodes / reconcile_nodes are both properly
registered in CELERY_BEAT_SCHEDULE (unlike the backup-schedule bug, this
wiring is correct) but had zero test coverage before this file. Given
that the same "no coverage" signal predicted real bugs twice already
this session (backup schedules, IP reservation), this locks in the
currently-correct behavior of node offline detection and reconciliation
against regression, since both are exactly the kind of "the DB looks
fine but reality has drifted" logic this project is built to get right.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events.models import Event
from apps.nodes.models import NodeAdminState

pytestmark = pytest.mark.django_db


# --- mark_offline_if_stale -------------------------------------------


def test_a_fresh_node_is_not_marked_offline(node):
    from apps.nodes.services import mark_offline_if_stale

    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])

    assert mark_offline_if_stale(node) is False
    assert not Event.objects.filter(type="NODE_OFFLINE").exists()


def test_a_stale_node_is_marked_offline_and_emits_one_event(node):
    from apps.nodes.services import mark_offline_if_stale

    node.last_seen = timezone.now() - timedelta(seconds=120)
    node.save(update_fields=["last_seen"])

    assert mark_offline_if_stale(node) is True
    assert Event.objects.filter(type="NODE_OFFLINE", resource_id=str(node.uuid)).count() == 1


def test_a_node_that_never_sent_a_heartbeat_is_offline(node):
    from apps.nodes.services import mark_offline_if_stale

    assert node.last_seen is None
    assert mark_offline_if_stale(node) is True


def test_it_does_not_re_fire_for_the_same_offline_period(node):
    """The dedup window is keyed off `created_at__gte=node.last_seen`, so
    calling this repeatedly while nothing about the node changes (as the
    15s sweep does) must only ever emit one NODE_OFFLINE event."""
    from apps.nodes.services import mark_offline_if_stale

    node.last_seen = timezone.now() - timedelta(seconds=120)
    node.save(update_fields=["last_seen"])

    assert mark_offline_if_stale(node) is True
    assert mark_offline_if_stale(node) is False
    assert mark_offline_if_stale(node) is False
    assert Event.objects.filter(type="NODE_OFFLINE", resource_id=str(node.uuid)).count() == 1


def test_it_fires_again_after_the_node_recovers_and_goes_offline_again(node):
    """A real second incident: the first NODE_OFFLINE genuinely happened
    some real wall-clock time ago (backdated here rather than faked with
    time.sleep), the node then recovered, and has now gone stale again.
    Both `mark_offline_if_stale` and its `already_notified` dedup query
    use the real `timezone.now()`/auto_now_add clock, so `last_seen` must
    stay realistic here too -- it's never set to a time earlier than a
    prior event's `created_at`, which could never happen for a real
    heartbeat (last_seen only ever advances forward in time)."""
    from apps.nodes.services import mark_offline_if_stale

    node.last_seen = timezone.now() - timedelta(seconds=120)
    node.save(update_fields=["last_seen"])
    assert mark_offline_if_stale(node) is True
    Event.objects.filter(type="NODE_OFFLINE", resource_id=str(node.uuid)).update(created_at=timezone.now() - timedelta(hours=1))

    # Agent reconnects -- a fresh heartbeat moves last_seen forward.
    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])
    assert mark_offline_if_stale(node) is False  # online again, nothing to report

    # Goes offline a second time (last_seen only 120s stale, not another
    # full hour -- unlike the first incident's now-backdated event).
    node.last_seen = timezone.now() - timedelta(seconds=120)
    node.save(update_fields=["last_seen"])
    assert mark_offline_if_stale(node) is True

    assert Event.objects.filter(type="NODE_OFFLINE", resource_id=str(node.uuid)).count() == 2


def test_a_node_in_maintenance_is_never_marked_offline(node):
    from apps.nodes.services import mark_offline_if_stale

    node.admin_state = NodeAdminState.MAINTENANCE
    node.last_seen = timezone.now() - timedelta(seconds=120)
    node.save(update_fields=["admin_state", "last_seen"])

    assert mark_offline_if_stale(node) is False


def test_sweep_excludes_maintenance_and_disabled_nodes(organization):
    from apps.nodes.models import Node
    from apps.nodes.tasks import sweep_offline_nodes

    stale = timezone.now() - timedelta(seconds=120)
    Node.objects.create(organization=organization, name="active", hostname="active.local", last_seen=stale)
    Node.objects.create(organization=organization, name="maint", hostname="maint.local", last_seen=stale, admin_state=NodeAdminState.MAINTENANCE)
    Node.objects.create(organization=organization, name="disabled", hostname="disabled.local", last_seen=stale, admin_state=NodeAdminState.DISABLED)

    changed = sweep_offline_nodes()

    assert changed == 1
    assert Event.objects.filter(type="NODE_OFFLINE").count() == 1


# --- reconciliation ---------------------------------------------------


def test_reconcile_node_is_a_noop_when_the_node_is_not_online(node):
    from apps.nodes.reconciliation import reconcile_node

    assert node.last_seen is None  # -> OFFLINE
    assert reconcile_node(node) is False


def test_reconcile_node_is_a_noop_when_counts_match(node):
    from apps.nodes.reconciliation import reconcile_node

    node.last_seen = timezone.now()
    node.reported_vm_count = 0
    node.save(update_fields=["last_seen", "reported_vm_count"])

    assert reconcile_node(node) is False


def test_reconcile_node_emits_a_mismatch_event_when_counts_diverge(node, organization, project):
    from apps.nodes.reconciliation import reconcile_node
    from apps.virtual_machines.models import VirtualMachine

    node.last_seen = timezone.now()
    node.reported_vm_count = 3  # agent says 3, DB will only have 1
    node.save(update_fields=["last_seen", "reported_vm_count"])
    VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="RUNNING")

    assert reconcile_node(node) is True
    event = Event.objects.get(type="RECONCILIATION_MISMATCH", resource_id=str(node.uuid))
    assert event.metadata == {"database_vm_count": 1, "agent_reported_vm_count": 3}


def test_reconcile_node_excludes_vms_that_are_deleting(node, organization, project):
    """A VM mid-DELETE is expected to still exist on the hypervisor for a
    moment -- it shouldn't count as drift."""
    from apps.nodes.reconciliation import reconcile_node
    from apps.virtual_machines.models import VirtualMachine

    node.last_seen = timezone.now()
    node.reported_vm_count = 0
    node.save(update_fields=["last_seen", "reported_vm_count"])
    VirtualMachine.objects.create(organization=organization, project=project, node=node, name="going-away", status="DELETING")

    assert reconcile_node(node) is False


def test_reconcile_all_aggregates_across_nodes(organization):
    from apps.nodes.models import Node
    from apps.nodes.reconciliation import reconcile_all

    matching = Node.objects.create(organization=organization, name="a", hostname="a.local", last_seen=timezone.now(), reported_vm_count=0)
    mismatched = Node.objects.create(organization=organization, name="b", hostname="b.local", last_seen=timezone.now(), reported_vm_count=5)
    offline = Node.objects.create(organization=organization, name="c", hostname="c.local", reported_vm_count=5)

    assert reconcile_all() == 1
    assert Event.objects.filter(type="RECONCILIATION_MISMATCH", resource_id=str(mismatched.uuid)).exists()
    assert not Event.objects.filter(type="RECONCILIATION_MISMATCH", resource_id=str(matching.uuid)).exists()
    assert not Event.objects.filter(type="RECONCILIATION_MISMATCH", resource_id=str(offline.uuid)).exists()
