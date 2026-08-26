from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.jobs.models import Job


class JobConsumer(AsyncJsonWebsocketConsumer):
    """/ws/jobs/{job_uuid} -- streams Job progress updates in real time."""

    async def connect(self):
        self.job_uuid = self.scope["url_route"]["kwargs"]["job_uuid"]
        job = await self._get_job()
        if job is None or not await self._user_can_view(job):
            await self.close(code=4403)
            return
        self.group_name = f"job.{self.job_uuid}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "job.snapshot", "job": await self._serialize(job)})

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def job_update(self, event):
        await self.send_json(event)

    @database_sync_to_async
    def _get_job(self):
        return Job.objects.select_related("organization").filter(uuid=self.job_uuid).first()

    @database_sync_to_async
    def _user_can_view(self, job) -> bool:
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            return False
        from apps.permissions.policies import has_permission

        return has_permission(user, job.organization, "job.view")

    @database_sync_to_async
    def _serialize(self, job):
        return {
            "uuid": str(job.uuid),
            "type": job.type,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "error": job.error,
        }
