from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.webhooks.models import Webhook, WebhookDelivery
from apps.webhooks.serializers import WebhookCreateSerializer, WebhookDeliverySerializer, WebhookSerializer


class WebhookViewSet(OrganizationScopedModelViewSet):
    queryset = Webhook.objects.select_related("organization").all()
    serializer_class = WebhookSerializer
    permission_map = {
        "list": "webhook.manage", "retrieve": "webhook.manage", "create": "webhook.manage",
        "update": "webhook.manage", "partial_update": "webhook.manage", "destroy": "webhook.manage",
        "deliveries": "webhook.manage",
    }
    filterset_fields = ["enabled"]
    search_fields = ["name", "url"]

    def get_serializer_class(self):
        if self.action == "create":
            return WebhookCreateSerializer
        return WebhookSerializer

    def get_throttles(self):
        if self.action in {"create", "update", "partial_update"}:
            self.throttle_scope = "webhook"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=["get"])
    def deliveries(self, request, uuid=None):
        webhook = self.get_object()
        page = self.paginate_queryset(webhook.deliveries.all())
        serializer = WebhookDeliverySerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
