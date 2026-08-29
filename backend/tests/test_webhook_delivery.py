"""
Regression test for a webhook SSRF bypass: WebhookSerializer.validate_url
only rejects private/loopback/link-local hosts at *creation* time
(apps.webhooks.serializers._is_private_host). requests.post follows
redirects by default, so a webhook target that responds with a 3xx to an
internal address (e.g. cloud metadata, localhost services) made that
create-time check purely cosmetic -- the delivery would transparently
follow the redirect. See apps.webhooks.tasks.deliver_webhook.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.webhooks.models import DeliveryStatus, Webhook, WebhookDelivery
from apps.webhooks.tasks import deliver_webhook

pytestmark = pytest.mark.django_db


@pytest.fixture
def webhook(organization):
    return Webhook.objects.create(organization=organization, name="test-hook", url="https://attacker.example/hook", events=["*"])


@pytest.fixture
def delivery(webhook):
    return WebhookDelivery.objects.create(webhook=webhook, event_type="vm.created", payload={"vm_uuid": "x"})


def test_delivery_request_disables_redirects(delivery):
    """The actual, load-bearing assertion: whatever `requests.post` is
    called with must include allow_redirects=False, or a webhook target
    (or anyone able to make it respond 3xx) can point the controller's
    outbound request at an internal address after the create-time host
    check already passed."""
    with patch("apps.webhooks.tasks.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "ok"
        deliver_webhook(delivery.pk)

    assert mock_post.call_args.kwargs.get("allow_redirects") is False


def test_a_redirect_response_is_treated_as_a_failed_delivery_not_success(delivery):
    """Belt-and-suspenders: even if the kwarg were ever dropped by
    accident, a 3xx must not be recorded as SUCCESS."""
    with patch("apps.webhooks.tasks.requests.post") as mock_post:
        mock_post.return_value.status_code = 302
        mock_post.return_value.text = ""
        with pytest.raises(Exception):
            deliver_webhook(delivery.pk)

    delivery.refresh_from_db()
    assert delivery.status != DeliveryStatus.SUCCESS
