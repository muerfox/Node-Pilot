from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.storage import services
from apps.storage.models import StoragePool
from apps.storage.serializers import StoragePoolSerializer


class StoragePoolViewSet(OrganizationScopedModelViewSet):
    queryset = StoragePool.objects.select_related("node", "node__organization").all()
    serializer_class = StoragePoolSerializer
    organization_field_path = "node__organization"
    permission_map = {
        "list": "storage.view",
        "retrieve": "storage.view",
        "create": "storage.manage",
        "update": "storage.manage",
        "partial_update": "storage.manage",
        "destroy": "storage.manage",
    }
    filterset_fields = ["node", "type", "status", "enabled"]
    search_fields = ["name", "path"]

    def perform_create(self, serializer):
        data = serializer.validated_data
        pool, job = services.create_storage_pool(
            node=data["node"], name=data["name"], type=data["type"], path=data["path"],
            shared=data.get("shared", False), enabled=data.get("enabled", True),
            capabilities=data.get("capabilities"), requested_by=self.request.user,
        )
        log_from_request(self.request, action="STORAGE_POOL_CREATE", resource_type="StoragePool", resource_id=str(pool.uuid), organization=pool.node.organization, metadata={"job_id": str(job.uuid)})
        serializer.instance = pool
