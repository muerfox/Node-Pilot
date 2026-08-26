from django.urls import re_path

from apps.jobs.consumers import JobConsumer

websocket_urlpatterns = [
    re_path(r"^ws/jobs/(?P<job_uuid>[0-9a-fA-F-]{36})/?$", JobConsumer.as_asgi()),
]
