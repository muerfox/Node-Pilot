from __future__ import annotations

import hashlib
import hmac
import json
import logging

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.webhooks.models import DeliveryStatus, WebhookDelivery

logger = logging.getLogger("nodepilot.webhooks")

REQUEST_TIMEOUT_SECONDS = 10


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@shared_task(bind=True, max_retries=None)
def deliver_webhook(self, delivery_id: int) -> None:
    delivery = WebhookDelivery.objects.select_related("webhook").get(pk=delivery_id)
    webhook = delivery.webhook
    max_retries = settings.NODEPILOT["WEBHOOK_MAX_RETRIES"]

    body = json.dumps({"event": delivery.event_type, "data": delivery.payload, "delivery_id": str(delivery.uuid)}).encode()
    signature = sign_payload(webhook.secret, body)

    delivery.attempt += 1
    try:
        response = requests.post(
            webhook.url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-NodePilot-Event": delivery.event_type,
                "X-NodePilot-Signature": f"sha256={signature}",
                "X-NodePilot-Delivery": str(delivery.uuid),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
            # WebhookSerializer.validate_url only rejects private/loopback/
            # link-local hosts at creation time -- following a redirect
            # here would let a webhook target (or anyone able to make it
            # respond with a 3xx, e.g. an open redirector) point this
            # server-side request at an internal address after the fact,
            # making the create-time check purely cosmetic. A legitimate
            # receiver has no need to redirect a webhook delivery.
            allow_redirects=False,
        )
        delivery.response_status = response.status_code
        delivery.response_body = response.text[:2000]

        if 200 <= response.status_code < 300:
            delivery.status = DeliveryStatus.SUCCESS
            delivery.delivered_at = timezone.now()
            delivery.save(update_fields=["attempt", "response_status", "response_body", "status", "delivered_at"])
            return

        raise requests.HTTPError(f"Webhook endpoint returned {response.status_code}")

    except Exception as exc:
        delivery.response_body = str(exc)[:2000]
        if delivery.attempt >= max_retries:
            delivery.status = DeliveryStatus.FAILED
            delivery.save(update_fields=["attempt", "response_status", "response_body", "status"])
            logger.error("Webhook delivery %s permanently failed after %s attempts: %s", delivery.uuid, delivery.attempt, exc)
            return

        delivery.status = DeliveryStatus.RETRYING
        delivery.save(update_fields=["attempt", "response_status", "response_body", "status"])
        backoff_seconds = min(2**delivery.attempt, 300)  # exponential backoff, capped at 5 minutes
        raise self.retry(exc=exc, countdown=backoff_seconds, max_retries=max_retries)
