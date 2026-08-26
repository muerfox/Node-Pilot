from __future__ import annotations

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.authentication.models import APIToken


class APITokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates requests carrying `Authorization: Token <raw-token>`.
    Distinct from JWT's `Bearer` scheme so both can coexist as configured
    DEFAULT_AUTHENTICATION_CLASSES.
    """

    keyword = "Token"

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).split()
        if not auth_header or auth_header[0].decode() != self.keyword:
            return None
        if len(auth_header) != 2:
            raise exceptions.AuthenticationFailed("Invalid token header.")

        raw_token = auth_header[1].decode()
        token_hash = APIToken.hash_token(raw_token)
        try:
            token = APIToken.objects.select_related("user").get(token_hash=token_hash)
        except APIToken.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid API token.") from exc

        if not token.is_valid:
            raise exceptions.AuthenticationFailed("This API token has expired or been revoked.")
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed("User account is disabled.")

        token.mark_used()
        request.api_token = token
        return (token.user, token)
