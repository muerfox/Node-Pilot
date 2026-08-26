import re
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.nodes.models import NodeAdminState, NodeStatus
from apps.virtual_machines.mac import generate_mac_address

pytestmark = pytest.mark.django_db


def test_generate_mac_address_format():
    mac = generate_mac_address()
    assert re.match(r"^52:54:00:[0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2}$", mac)


def test_node_with_no_heartbeat_is_offline(node):
    assert node.last_seen is None
    assert node.effective_status() == NodeStatus.OFFLINE


def test_node_with_recent_heartbeat_is_online(node):
    node.last_seen = timezone.now()
    node.save(update_fields=["last_seen"])
    assert node.effective_status() == NodeStatus.ONLINE


def test_node_with_stale_heartbeat_is_offline(settings, node):
    settings.NODEPILOT = {**settings.NODEPILOT, "OFFLINE_THRESHOLD_SECONDS": 30}
    node.last_seen = timezone.now() - timedelta(seconds=60)
    node.save(update_fields=["last_seen"])
    assert node.effective_status() == NodeStatus.OFFLINE


def test_node_in_maintenance_reports_maintenance_regardless_of_heartbeat(node):
    node.admin_state = NodeAdminState.MAINTENANCE
    node.last_seen = timezone.now()
    node.save(update_fields=["admin_state", "last_seen"])
    assert node.effective_status() == NodeStatus.MAINTENANCE
    assert node.is_schedulable() is False
