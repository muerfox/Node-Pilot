from django.contrib import admin

from apps.events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["type", "severity", "resource_type", "resource_id", "organization", "created_at"]
    list_filter = ["severity", "type"]

    def has_add_permission(self, request):
        return False
