from django.urls import re_path

from apps.nodes.consumers import AgentConsumer, NodeStatusConsumer

websocket_urlpatterns = [
    re_path(r"^ws/agent/(?P<node_uuid>[0-9a-fA-F-]{36})/?$", AgentConsumer.as_asgi()),
    re_path(r"^ws/nodes/(?P<node_uuid>[0-9a-fA-F-]{36})/?$", NodeStatusConsumer.as_asgi()),
]
