"""
/api/v1/ -- the complete versioned REST surface (section 31). Each domain
app owns its own urls.py (ViewSet routers + any custom endpoints); this
module just aggregates them under one prefix so the API stays
backwards-compatible within a major version by construction -- a new
resource is a new include(), not a restructuring of existing ones.
"""
from django.urls import include, path

urlpatterns = [
    path("", include("apps.authentication.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.organizations.urls")),
    path("", include("apps.permissions.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.nodes.urls")),
    path("", include("apps.jobs.urls")),
    path("", include("apps.virtual_machines.urls")),
    path("", include("apps.storage.urls")),
    path("", include("apps.networks.urls")),
    path("", include("apps.images.urls")),
    path("", include("apps.vm_templates.urls")),
    path("", include("apps.snapshots.urls")),
    path("", include("apps.backups.urls")),
    path("", include("apps.metrics.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.webhooks.urls")),
]
