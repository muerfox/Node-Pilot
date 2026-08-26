from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedReadOnlyViewSet
from apps.jobs.models import Job
from apps.jobs.serializers import JobSerializer
from apps.jobs.services import request_cancel


class JobViewSet(OrganizationScopedReadOnlyViewSet):
    """Jobs are created internally by domain services, never directly via
    POST -- clients can only list/retrieve/cancel them."""

    queryset = Job.objects.select_related("organization", "node", "created_by").all()
    serializer_class = JobSerializer
    permission_map = {
        "list": "job.view",
        "retrieve": "job.view",
        "cancel": "job.manage",
    }
    filterset_fields = ["status", "type", "resource_type", "resource_id", "node"]
    search_fields = ["resource_id", "message"]
    ordering_fields = ["created_at", "finished_at"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        job = self.get_object()
        updated = request_cancel(job)
        log_from_request(request, action="JOB_CANCEL", resource_type="Job", resource_id=str(job.uuid), organization=job.organization)
        return Response(JobSerializer(updated).data)
