from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor_label", "action", "resource_type", "resource_id", "result"]
    list_filter = ["action", "resource_type", "result"]
    search_fields = ["actor_label", "resource_id"]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
