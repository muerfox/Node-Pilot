"""
apps.events.services.emit_event's own webhook dispatch used to convert
"NODE_OFFLINE" into "node_offline" (a naive .lower()) -- but
apps.webhooks.models.SUPPORTED_EVENTS and every Webhook's own `events`
list use dotted "resource.action" form ("node.offline"), matching what
WebhookSerializer.validate_events actually accepts. A webhook subscribed
to the one value the API lets it subscribe to never matched, so it never
fired for anything but VM events -- only a wildcard ("*") subscription
ever saw node/backup/network/snapshot events at all.

Separately, apps.virtual_machines.tasks._emit_vm_event used to call
dispatch_event a second time, itself, with its own ad-hoc conversion
(mostly right for VM_* types, by luck) *in addition to* the dispatch
emit_event already does internally -- so a wildcard-subscribed webhook
got every VM event delivered twice, in two different payload shapes.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.events.services import _webhook_event_type, emit_event
from apps.webhooks.models import Webhook, WebhookDelivery
from apps.virtual_machines.models import VirtualMachine
from apps.virtual_machines.tasks import _emit_vm_event

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "raw_type,expected",
    [
        ("NODE_OFFLINE", "node.offline"),
        ("NODE_ONLINE", "node.online"),
        ("VM_CREATED", "vm.created"),
        ("VM_STARTED", "vm.started"),
        ("BACKUP_COMPLETED", "backup.completed"),
        ("BACKUP_FAILED", "backup.failed"),
        ("VM_SNAPSHOT_CREATED", "vm.snapshot_created"),
        ("SINGLEWORD", "singleword"),
    ],
)
def test_webhook_event_type_conversion(raw_type, expected):
    assert _webhook_event_type(raw_type) == expected


@pytest.fixture
def fake_deliver(monkeypatch):
    # dispatch_event enqueues deliver_webhook.delay(...), and
    # CELERY_TASK_ALWAYS_EAGER=True in tests runs it inline -- stub the
    # actual HTTP delivery so this stays a pure dispatch-matching test.
    monkeypatch.setattr("apps.webhooks.tasks.resolve_safe_ip", lambda hostname: "203.0.113.1")
    with patch("apps.webhooks.tasks.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "ok"
        yield mock_post


@pytest.fixture
def node_offline_webhook(organization):
    return Webhook.objects.create(organization=organization, name="node-hook", url="https://example.com/hook", events=["node.offline"])


def test_a_webhook_scoped_to_node_offline_actually_receives_it(organization, node, fake_deliver, node_offline_webhook):

    emit_event(type="NODE_OFFLINE", severity="CRITICAL", resource_type="Node", resource_id=str(node.uuid), organization=organization, metadata={})

    deliveries = WebhookDelivery.objects.filter(webhook=node_offline_webhook)
    assert deliveries.count() == 1
    assert deliveries.get().event_type == "node.offline"


def test_a_webhook_scoped_to_a_different_event_does_not_receive_node_offline(organization, node, fake_deliver, node_offline_webhook):
    other = Webhook.objects.create(organization=organization, name="vm-hook", url="https://example.com/hook2", events=["vm.created"])

    emit_event(type="NODE_OFFLINE", severity="CRITICAL", resource_type="Node", resource_id=str(node.uuid), organization=organization, metadata={})

    assert not WebhookDelivery.objects.filter(webhook=other).exists()


@pytest.fixture
def wildcard_webhook(organization):
    return Webhook.objects.create(organization=organization, name="wildcard", url="https://example.com/all", events=["*"])


@pytest.fixture
def vm(organization, project, node):
    return VirtualMachine.objects.create(organization=organization, project=project, node=node, name="web-01", status="STOPPED")


def test_a_vm_event_is_delivered_exactly_once_to_a_wildcard_webhook(wildcard_webhook, vm, fake_deliver):
    """The double-dispatch regression: this used to create two
    WebhookDelivery rows for one VM_CREATED event."""

    _emit_vm_event(vm, "VM_CREATED")

    deliveries = WebhookDelivery.objects.filter(webhook=wildcard_webhook)
    assert deliveries.count() == 1
    delivery = deliveries.get()
    assert delivery.event_type == "vm.created"
    assert delivery.payload["resource_id"] == str(vm.uuid)
    assert delivery.payload["name"] == vm.name


def test_a_vm_event_still_reaches_a_specifically_scoped_webhook(organization, vm, fake_deliver):
    scoped = Webhook.objects.create(organization=organization, name="vm-created-hook", url="https://example.com/vm", events=["vm.created"])

    _emit_vm_event(vm, "VM_CREATED")

    assert WebhookDelivery.objects.filter(webhook=scoped).count() == 1
