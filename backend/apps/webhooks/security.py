"""
SSRF defenses for webhook delivery (section 46).

Two distinct checks live here, because a "checked once, used later" gap
is not the same problem as a "checked and connected in the same breath"
one:

- `is_private_host` is a plain resolve-and-check, good enough for
  create-time validation (`WebhookSerializer.validate_url`) where all
  that matters is rejecting an obviously bad URL up front.
- `resolve_safe_ip` + `pinned_dns` are for delivery time: they resolve
  once, validate every candidate address, and then force the HTTP
  client's own DNS lookup to return that exact validated address rather
  than re-resolving -- closing the DNS-rebinding gap where a webhook is
  created against a benign IP and its DNS record is later repointed at
  an internal address before delivery happens.
"""
from __future__ import annotations

import ipaddress
import socket
from contextlib import contextmanager
from typing import Iterator


class UnsafeWebhookHostError(Exception):
    """A webhook hostname is (or resolves to) private/loopback/link-local/
    reserved address space, or could not be resolved at all."""


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


def is_private_host(hostname: str) -> bool:
    """Best-effort check for create-time validation. Does not pin
    anything, so on its own it does not defend against DNS rebinding --
    see `resolve_safe_ip` for the delivery-time check that does."""
    try:
        return _is_unsafe_ip(ipaddress.ip_address(hostname))
    except ValueError:
        pass  # Not a literal IP; resolve it.
    try:
        for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if _is_unsafe_ip(ipaddress.ip_address(sockaddr[0])):
                return True
    except socket.gaierror:
        return True  # Can't resolve it -- reject rather than risk surprises.
    return False


def resolve_safe_ip(hostname: str) -> str:
    """Resolve `hostname` to a single IP, verifying every candidate the
    resolver returns is public. Raises `UnsafeWebhookHostError` if any
    candidate is private/loopback/link-local/reserved, or if resolution
    fails outright. The returned address is meant to be pinned via
    `pinned_dns` for the delivery attempt that follows."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if _is_unsafe_ip(literal):
            raise UnsafeWebhookHostError(f"{hostname} is a private/loopback/link-local/reserved address")
        return hostname

    try:
        candidates = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeWebhookHostError(f"could not resolve {hostname}") from exc

    if not candidates:
        raise UnsafeWebhookHostError(f"could not resolve {hostname}")

    for _, _, _, _, sockaddr in candidates:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_unsafe_ip(ip):
            raise UnsafeWebhookHostError(f"{hostname} resolves to private address {ip}")

    return str(ipaddress.ip_address(candidates[0][4][0]))


@contextmanager
def pinned_dns(hostname: str, ip: str) -> Iterator[None]:
    """While active, force any `socket.getaddrinfo(hostname, ...)` call
    to resolve to `ip` instead of performing a fresh DNS lookup -- so the
    HTTP client used for the actual delivery can't be steered to a
    different (possibly private) address than the one `resolve_safe_ip`
    just validated. Scoped to a single outbound call in a Celery task, so
    the global monkeypatch is restored before anything else in this
    worker process observes it.
    """
    pinned_family = socket.AF_INET6 if ipaddress.ip_address(ip).version == 6 else socket.AF_INET
    original_getaddrinfo = socket.getaddrinfo

    def patched(host, port=0, family=0, type=0, proto=0, flags=0):
        if host == hostname:
            sockaddr = (ip, port, 0, 0) if pinned_family == socket.AF_INET6 else (ip, port)
            return [(pinned_family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]
        return original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = patched
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
