from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import log_from_request
from apps.backups import services
from apps.backups.models import Backup, BackupSchedule, BackupTarget
from apps.backups.serializers import BackupScheduleSerializer, BackupSerializer, BackupTargetSerializer
from apps.common.viewsets import OrganizationScopedModelViewSet


class BackupTargetViewSet(OrganizationScopedModelViewSet):
    queryset = BackupTarget.objects.select_related("organization").all()
    serializer_class = BackupTargetSerializer
    permission_map = {
        "list": "backup.view", "retrieve": "backup.view", "create": "backup.create",
        "update": "backup.create", "partial_update": "backup.create", "destroy": "backup.delete",
    }
    filterset_fields = ["type", "enabled"]
    search_fields = ["name"]


class BackupViewSet(OrganizationScopedModelViewSet):
    queryset = Backup.objects.select_related("vm", "vm__organization", "target").all()
    serializer_class = BackupSerializer
    organization_field_path = "vm__organization"
    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_map = {
        "list": "backup.view", "retrieve": "backup.view", "create": "backup.create",
        "destroy": "backup.delete", "restore": "backup.restore",
    }
    filterset_fields = ["vm", "target", "status", "type"]

    def create(self, request, *args, **kwargs):
        serializer = BackupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vm = serializer.validated_data["vm"]
        job = services.create_backup(vm, serializer.validated_data["target"], backup_type=serializer.validated_data["type"], requested_by=request.user)
        log_from_request(request, action="BACKUP_CREATE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        backup = self.get_object()
        services.delete_backup(backup)
        log_from_request(request, action="BACKUP_DELETE", resource_type="Backup", resource_id=str(backup.uuid), organization=backup.vm.organization)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def restore(self, request, uuid=None):
        backup = self.get_object()
        job = services.restore_backup(backup, request.user)
        log_from_request(request, action="BACKUP_RESTORE", resource_type="Backup", resource_id=str(backup.uuid), organization=backup.vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)


class BackupScheduleViewSet(OrganizationScopedModelViewSet):
    queryset = BackupSchedule.objects.select_related("organization", "vm", "target").all()
    serializer_class = BackupScheduleSerializer
    permission_map = {
        "list": "backup.view", "retrieve": "backup.view", "create": "backup.create",
        "update": "backup.create", "partial_update": "backup.create", "destroy": "backup.delete",
    }
    filterset_fields = ["vm", "target", "enabled"]

    def perform_create(self, serializer):
        data = serializer.validated_data
        schedule = services.create_schedule(
            organization=data["organization"], vm=data["vm"], target=data["target"], backup_type=data["backup_type"],
            cron_expression=data["cron_expression"], timezone_name=data.get("timezone", "UTC"), retention_days=data.get("retention_days", 30),
        )
        serializer.instance = schedule

    def perform_destroy(self, instance):
        services.delete_schedule(instance)
