"""
Rate limiting differentiated by principal type (section 64): anonymous,
authenticated user, API token, and administrator each get a distinct
throttle scope. DRF's AnonRateThrottle/UserRateThrottle already split
anonymous vs. authenticated by "anon"/"user" rates in
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]; these two extend that split
further for API tokens and admins.
"""
from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle


class APITokenRateThrottle(SimpleRateThrottle):
    """Applies a distinct, generally tighter rate to requests authenticated
    via an APIToken (as opposed to an interactive JWT session)."""

    scope = "api_token"

    def get_cache_key(self, request, view):
        token = getattr(request, "auth", None)
        if token is None or not hasattr(token, "token_hash"):
            return None  # Not an API-token-authenticated request; skip.
        return self.cache_format % {"scope": self.scope, "ident": token.token_hash}


class AdminExemptRateThrottle(SimpleRateThrottle):
    """Staff/superusers are exempt from the standard per-user rate --
    operators shouldn't get locked out of their own platform during an
    incident."""

    scope = "user"

    def allow_request(self, request, view):
        if request.user and (request.user.is_staff or request.user.is_superuser):
            return True
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
