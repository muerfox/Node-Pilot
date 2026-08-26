from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class EventsConsumer(AsyncJsonWebsocketConsumer):
    """/ws/events?organization={uuid} -- live event stream for one org."""

    async def connect(self):
        self.org_uuid = self.scope["url_route"]["kwargs"].get("org_uuid") or _query_param(self.scope, "organization")
        organization = await self._get_organization()
        if organization is None or not await self._can_view(organization):
            await self.close(code=4403)
            return
        self.group_name = f"events.{organization.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def event_message(self, event):
        await self.send_json(event["event"])

    @database_sync_to_async
    def _get_organization(self):
        from apps.organizations.models import Organization

        return Organization.objects.filter(uuid=self.org_uuid).first() if self.org_uuid else None

    @database_sync_to_async
    def _can_view(self, organization) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        from apps.permissions.policies import has_permission

        return has_permission(user, organization, "event.view")


def _query_param(scope, name: str) -> str | None:
    from urllib.parse import parse_qs

    query = parse_qs(scope.get("query_string", b"").decode())
    values = query.get(name)
    return values[0] if values else None
