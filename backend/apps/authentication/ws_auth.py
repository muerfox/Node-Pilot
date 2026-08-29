"""
WebSocket authentication for Channels consumers.

The REST API is JWT-first (section 32); Django Channels' built-in
`AuthMiddlewareStack` only recognizes the session cookie, which a
JWT-authenticated single-page frontend never sets. Rather than carry the
JWT access token itself in the WebSocket URL -- a browser can't attach
an `Authorization` header to a WS handshake, so the URL is the only
option, and that risks the token landing in proxy/server access logs --
the frontend first exchanges it for a short-lived, single-use ticket via
`POST /api/v1/auth/ws-ticket/` (an ordinary authenticated HTTPS request,
which *does* support headers). This middleware redeems that ticket
(apps.authentication.ws_ticket.redeem_ticket) from the WebSocket URL's
`?ticket=` query parameter and resolves `scope["user"]` accordingly, so
every consumer's existing `user.is_authenticated` /
`has_permission(...)` checks work unchanged.

An invalid, expired, or already-used ticket simply leaves
`scope["user"]` as AnonymousUser -- consumers already reject that with a
4403 close code, so there's no separate "auth failed" path to maintain
here.
"""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_ticket(ticket: str):
    from apps.authentication.ws_ticket import redeem_ticket
    from apps.users.models import User

    user_uuid = redeem_ticket(ticket)
    if user_uuid is None:
        return AnonymousUser()
    try:
        return User.objects.get(uuid=user_uuid, is_active=True)
    except (User.DoesNotExist, ValueError):
        return AnonymousUser()


class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        ticket = (query.get("ticket") or [None])[0]
        scope["user"] = await _user_from_ticket(ticket) if ticket else AnonymousUser()
        return await super().__call__(scope, receive, send)


def TicketAuthMiddlewareStack(inner):
    return TicketAuthMiddleware(inner)
