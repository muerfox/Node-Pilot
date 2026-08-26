from django.urls import re_path

from apps.virtual_machines.consumers import ConsoleConsumer, VMConsumer

websocket_urlpatterns = [
    re_path(r"^ws/vms/(?P<vm_uuid>[0-9a-fA-F-]{36})/?$", VMConsumer.as_asgi()),
    re_path(r"^ws/console/(?P<vm_uuid>[0-9a-fA-F-]{36})/?$", ConsoleConsumer.as_asgi()),
]
