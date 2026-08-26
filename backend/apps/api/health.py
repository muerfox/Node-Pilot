"""
Health endpoints (section 56). /health/live is a pure liveness check (the
process is up); /health/ready additionally verifies the dependencies the
controller cannot function without. Neither ever echoes configuration
values -- only boolean-ish status per dependency.
"""
from __future__ import annotations

from django.db import connections
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.redis_client import get_redis


class LivenessView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"status": "alive"})


class ReadinessView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checks = {"database": self._check_database(), "redis": self._check_redis()}
        healthy = all(checks.values())
        return Response({"status": "ready" if healthy else "not_ready", "checks": checks}, status=200 if healthy else 503)

    @staticmethod
    def _check_database() -> bool:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception:
            return False

    @staticmethod
    def _check_redis() -> bool:
        try:
            return bool(get_redis().ping())
        except Exception:
            return False
