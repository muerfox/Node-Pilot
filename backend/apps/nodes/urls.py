from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.nodes.views import HeartbeatView, NodeViewSet

router = DefaultRouter()
router.register("nodes", NodeViewSet, basename="node")

urlpatterns = [
    path("agent/heartbeat/", HeartbeatView.as_view(), name="agent-heartbeat"),
] + router.urls
