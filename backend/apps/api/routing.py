"""Aggregates every app's websocket_urlpatterns (section 36) for the ASGI
router in config/asgi.py."""
from apps.events.routing import websocket_urlpatterns as events_ws
from apps.jobs.routing import websocket_urlpatterns as jobs_ws
from apps.nodes.routing import websocket_urlpatterns as nodes_ws
from apps.virtual_machines.routing import websocket_urlpatterns as vms_ws

websocket_urlpatterns = [*jobs_ws, *nodes_ws, *vms_ws, *events_ws]
