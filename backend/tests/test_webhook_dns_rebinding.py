"""
Follow-up to the webhook SSRF-via-redirect fix (test_webhook_delivery.py):
WebhookSerializer.validate_url only ever checked the host once, at
creation time. Nothing stopped a webhook's DNS record from later being
repointed at an internal address before a delivery actually ran -- the
create-time check would have already passed and nothing re-validated it.
apps.webhooks.security.resolve_safe_ip/pinned_dns close that gap by
re-resolving and re-validating at delivery time and pinning the HTTP
client's connection to exactly the address just validated.
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from apps.webhooks.models import DeliveryStatus, Webhook, WebhookDelivery
from apps.webhooks.security import UnsafeWebhookHostError, is_private_host, pinned_dns, resolve_safe_ip
from apps.webhooks.tasks import deliver_webhook

pytestmark = pytest.mark.django_db


def _fake_getaddrinfo(ip: str):
    def fn(host, *_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))]

    return fn


def test_resolve_safe_ip_accepts_a_literal_public_ip():
    assert resolve_safe_ip("93.184.216.34") == "93.184.216.34"


def test_resolve_safe_ip_rejects_a_literal_private_ip():
    with pytest.raises(UnsafeWebhookHostError):
        resolve_safe_ip("10.0.0.5")


def test_resolve_safe_ip_rejects_a_hostname_that_resolves_privately(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(UnsafeWebhookHostError):
        resolve_safe_ip("attacker.example")


def test_resolve_safe_ip_accepts_a_hostname_that_resolves_publicly(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert resolve_safe_ip("attacker.example") == "93.184.216.34"


def test_pinned_dns_overrides_resolution_for_the_pinned_host_only(monkeypatch):
    """The core rebinding defense: once resolve_safe_ip has validated an
    address, pinned_dns must force *that exact address* for the
    duration of the request, even if the "real" resolver would return
    something else the second time around (simulating an attacker
    rebinding DNS between the check and the connect)."""
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.1"))  # what a rebound resolver would now say

    with pinned_dns("attacker.example", "93.184.216.34"):
        result = socket.getaddrinfo("attacker.example", 443)
        assert result[0][4][0] == "93.184.216.34"  # pinned value wins, not the rebound one
        # An unrelated host is unaffected by the pin.
        assert socket.getaddrinfo("other.example", 443)[0][4][0] == "10.0.0.1"

    # The monkeypatch is restored after the context exits.
    assert socket.getaddrinfo("attacker.example", 443)[0][4][0] == "10.0.0.1"


def test_pinned_dns_preserves_the_ipv6_family_and_sockaddr_shape():
    with pinned_dns("v6.example", "2606:2800:220:1:248:1893:25c8:1946"):
        family, _, _, _, sockaddr = socket.getaddrinfo("v6.example", 443)[0]
        assert family == socket.AF_INET6
        assert sockaddr[0] == "2606:2800:220:1:248:1893:25c8:1946"
        assert sockaddr[1] == 443


def test_is_private_host_still_works_for_create_time_validation(monkeypatch):
    assert is_private_host("10.0.0.5") is True
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert is_private_host("example.com") is False


@pytest.fixture
def webhook(organization):
    # A literal public IP avoids any real DNS lookup in validate_url at
    # creation time.
    return Webhook.objects.create(organization=organization, name="test-hook", url="https://93.184.216.34/hook", events=["*"])


@pytest.fixture
def delivery(webhook):
    return WebhookDelivery.objects.create(webhook=webhook, event_type="vm.created", payload={"vm_uuid": "x"})


def test_delivery_is_rejected_when_the_host_has_gone_unsafe_since_creation(delivery):
    """Simulates the rebinding scenario end to end: the host passed
    validation at creation time, but by delivery time it now resolves
    (or, here, literally is) unsafe. The delivery must fail cleanly
    without ever calling requests.post, and without being queued for
    retry."""
    with patch("apps.webhooks.tasks.resolve_safe_ip", side_effect=UnsafeWebhookHostError("now private")):
        with patch("apps.webhooks.tasks.requests.post") as mock_post:
            deliver_webhook(delivery.pk)
            mock_post.assert_not_called()

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.FAILED
    assert "now private" in delivery.response_body


def test_delivery_still_succeeds_when_the_host_is_still_safe(delivery):
    with patch("apps.webhooks.tasks.resolve_safe_ip", return_value="93.184.216.34"):
        with patch("apps.webhooks.tasks.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = "ok"
            deliver_webhook(delivery.pk)

    delivery.refresh_from_db()
    assert delivery.status == DeliveryStatus.SUCCESS
