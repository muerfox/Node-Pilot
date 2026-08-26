from django.contrib import admin

from apps.storage.models import StoragePool


@admin.register(StoragePool)
class StoragePoolAdmin(admin.ModelAdmin):
    list_display = ["name", "node", "type", "status", "shared", "enabled"]
    list_filter = ["type", "status", "shared"]
