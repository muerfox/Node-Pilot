from django.contrib import admin

from apps.authentication.models import APIToken


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "prefix", "revoked", "expires_at", "last_used_at"]
    readonly_fields = ["token_hash", "prefix"]
