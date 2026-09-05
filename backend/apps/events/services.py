from __future__ import annotations

import logging

from apps.events.models import Event

logger = logging.getLogger("nodepilot.events")


def _webhook_event_type(raw_type: str) -> str:
    """Event.type is UPPER_SNAKE_CASE (e.g. "NODE_OFFLINE", "VM_CREATED",
    "BACKUP_COMPLETED"), but apps.webhooks.models.SUPPORTED_EVENTS and
    every Webhook's own `events` subscription list use dotted
    "resource.action" form (e.g. "node.offline") -- section 37. A plain
    `.lower()` (what this used to do) produces "node_offline", which
    never matches a webhook actually subscribed to "node.offline": only
    a wildcard ("*") subscription would ever see it. Lowercase and turn
    the first underscore into a dot, matching every emitted type's
    RESOURCE_ACTION[_MORE] shape."""
    lowered = raw_type.lower()
    resource, sep, rest = lowered.partition("_")
    return f"{resource}.{rest}" if sep else lowered


def emit_event(*, type: str, severity: str, resource_type: str, resource_id: str, organization, actor=None, metadata: dict | None = None) -> Event:
    event = Event.objects.create(
        type=type, severity=severity, resource_type=resource_type, resource_id=resource_id,
        organization=organization, actor=actor, metadata=metadata or {},
    )

    _broadcast(event)

    try:
        from apps.webhooks.services import dispatch_event

        dispatch_event(organization, _webhook_event_type(type), {"resource_type": resource_type, "resource_id": resource_id, **(metadata or {})})
    except Exception:  # pragma: no cover
        logger.exception("Failed to dispatch webhooks for event %s", type)

    return event


def _broadcast(event: Event) -> None:
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        payload = {
            "uuid": str(event.uuid),
            "type": event.type,
            "severity": event.severity,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "created_at": event.created_at.isoformat(),
            "metadata": event.metadata,
        }
        async_to_sync(layer.group_send)(f"events.{event.organization_id}", {"type": "event.message", "event": payload})
    except Exception:  # pragma: no cover
        logger.exception("Failed to broadcast event %s", event.type)
