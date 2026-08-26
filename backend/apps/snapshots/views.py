from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.snapshots import services
from apps.snapshots.models import Snapshot
from apps.snapshots.serializers import SnapshotSerializer


class SnapshotViewSet(OrganizationScopedModelViewSet):
    queryset = Snapshot.objects.select_related("vm", "vm__organization").all()
    serializer_class = SnapshotSerializer
    organization_field_path = "vm__organization"
    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_map = {
        "list": "vm.view", "retrieve": "vm.view", "create": "vm.snapshot",
        "destroy": "vm.snapshot", "rollback": "vm.snapshot",
    }
    filterset_fields = ["vm", "status"]
    search_fields = ["name"]

    def create(self, request, *args, **kwargs):
        serializer = SnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vm = serializer.validated_data["vm"]
        job = services.create_snapshot(vm, name=serializer.validated_data["name"], description=serializer.validated_data.get("description", ""), requested_by=request.user)
        log_from_request(request, action="SNAPSHOT_CREATE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        snapshot = self.get_object()
        job = services.delete_snapshot(snapshot, request.user)
        log_from_request(request, action="SNAPSHOT_DELETE", resource_type="Snapshot", resource_id=str(snapshot.uuid), organization=snapshot.vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def rollback(self, request, uuid=None):
        snapshot = self.get_object()
        job = services.rollback_snapshot(snapshot, request.user)
        log_from_request(request, action="SNAPSHOT_ROLLBACK", resource_type="Snapshot", resource_id=str(snapshot.uuid), organization=snapshot.vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)
