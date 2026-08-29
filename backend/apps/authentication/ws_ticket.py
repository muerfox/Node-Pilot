"""
Short-lived, single-use WebSocket auth tickets.

The REST API is JWT-first, but a browser's WebSocket API cannot attach
an `Authorization` header to the handshake -- the only place to carry a
credential is the URL, which risks landing in proxy/server access logs
(see docs/architecture.md's security review section). Rather than put
the long-lived JWT access token there, the frontend first exchanges it
(over a normal authenticated HTTPS POST, which does support headers) for
a ticket that:

  * is only valid for TICKET_TTL_SECONDS
  * is deleted the instant it's redeemed, so even if a ticket *did* leak
    into a log line, replaying it after the real connection was
    established does nothing

`apps.authentication.ws_auth.JWTAuthMiddleware` redeems the ticket
(instead of decoding a JWT directly) for every WebSocket connection
under apps.api.routing -- jobs, VM/node status, events, and console.
"""
from __future__ import annotations

import secrets

from apps.common.redis_client import get_redis

TICKET_TTL_SECONDS = 30
_TICKET_KEY_PREFIX = "nodepilot:ws_ticket:"

# GET-then-DELETE as one atomic server-side operation, so two concurrent
# redemption attempts for the same ticket can't both succeed (the whole
# point of "single-use").
_REDEEM_SCRIPT = """
local v = redis.call("get", KEYS[1])
if v then
    redis.call("del", KEYS[1])
end
return v
"""


def issue_ticket(user) -> str:
    ticket = secrets.token_urlsafe(32)
    get_redis().set(f"{_TICKET_KEY_PREFIX}{ticket}", str(user.uuid), ex=TICKET_TTL_SECONDS)
    return ticket


def redeem_ticket(ticket: str) -> str | None:
    """Returns the associated user's uuid (as a string) and atomically
    deletes the ticket, or None if it's missing/expired/already used."""
    key = f"{_TICKET_KEY_PREFIX}{ticket}"
    return get_redis().eval(_REDEEM_SCRIPT, 1, key)
