from __future__ import annotations

import hashlib
import hmac
import json
import logging
from urllib.parse import urlparse

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.webhooks.models import DeliveryStatus, WebhookDelivery
from apps.webhooks.security import UnsafeWebhookHostError, pinned_dns, resolve_safe_ip

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
    hostname = urlparse(webhook.url).hostname

    try:
        # WebhookSerializer.validate_url already rejected private/
        # loopback/link-local hosts at creation time, but that check is
        # stale by the time a delivery actually happens -- a DNS record
        # can change in between. Re-resolve and re-validate now, then pin
        # the HTTP client's connection to exactly the address just
        # validated, so its own (separate) DNS lookup can't be steered
        # to something else in the gap between our check and its connect
        # (DNS rebinding).
        safe_ip = resolve_safe_ip(hostname)
        with pinned_dns(hostname, safe_ip):
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
                # A legitimate receiver has no need to redirect a webhook
                # delivery, and following one would sidestep the pinned
                # address entirely.
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

    except UnsafeWebhookHostError as exc:
        # Not worth retrying: an unsafe/unresolvable target isn't going
        # to fix itself before the next scheduled event re-triggers this
        # same check, and retrying an SSRF-flagged host is exactly the
        # kind of behavior we don't want.
        delivery.status = DeliveryStatus.FAILED
        delivery.response_body = str(exc)[:2000]
        delivery.save(update_fields=["attempt", "response_body", "status"])
        logger.warning("Webhook delivery %s rejected at delivery time: %s", delivery.uuid, exc)
        return

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
