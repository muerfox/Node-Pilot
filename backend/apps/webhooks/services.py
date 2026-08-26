from __future__ import annotations

from apps.webhooks.models import Webhook, WebhookDelivery


def dispatch_event(organization, event_type: str, payload: dict) -> list[WebhookDelivery]:
    """Fans an internal event out to every enabled Webhook subscribed to
    it, creating one WebhookDelivery per match and enqueueing delivery."""
    deliveries = []
    webhooks = Webhook.objects.filter(organization=organization, enabled=True)
    for webhook in webhooks:
        if not webhook.subscribes_to(event_type):
            continue
        delivery = WebhookDelivery.objects.create(webhook=webhook, event_type=event_type, payload=payload)
        deliveries.append(delivery)

    if deliveries:
        from apps.webhooks.tasks import deliver_webhook

        for delivery in deliveries:
            deliver_webhook.delay(delivery.pk)

    return deliveries
