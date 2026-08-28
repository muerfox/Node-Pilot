"""
WebSocket authentication for Channels consumers.

The REST API is JWT-first (section 32); Django Channels' built-in
`AuthMiddlewareStack` only recognizes the session cookie, which a
JWT-authenticated single-page frontend never sets. This middleware reads
the access token from the WebSocket URL's `?token=` query parameter
(sent by the frontend's `wsUrl()` helper) and resolves it the same way
`rest_framework_simplejwt.authentication.JWTAuthentication` would,
setting `scope["user"]` accordingly so every consumer's existing
`user.is_authenticated` / `has_permission(...)` checks work unchanged.

An invalid or missing token simply leaves `scope["user"]` as
AnonymousUser -- consumers already reject that with a 4403 close code,
so there's no separate "auth failed" path to maintain here.
"""
from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _user_from_token(raw_token: str):
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    from apps.users.models import User

    try:
        validated = AccessToken(raw_token)
        user_uuid = validated["user_uuid"]  # see SIMPLE_JWT["USER_ID_CLAIM"] in settings
        return User.objects.get(uuid=user_uuid, is_active=True)
    except (InvalidToken, TokenError, User.DoesNotExist, KeyError):
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):
    return JWTAuthMiddleware(inner)
