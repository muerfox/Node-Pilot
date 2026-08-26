from django.contrib import admin

from apps.nodes.models import Agent, Node


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ["name", "hostname", "organization", "admin_state", "last_seen"]
    list_filter = ["admin_state", "organization"]
    search_fields = ["name", "hostname", "fqdn"]


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ["node", "status", "token_prefix", "last_heartbeat_at"]
    readonly_fields = ["token_hash", "token_prefix"]
