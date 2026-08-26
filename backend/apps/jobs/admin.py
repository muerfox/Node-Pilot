from django.contrib import admin

from apps.jobs.models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["type", "status", "resource_type", "resource_id", "organization", "progress", "created_at"]
    list_filter = ["type", "status"]
    readonly_fields = [f.name for f in Job._meta.fields]

    def has_add_permission(self, request):
        return False
