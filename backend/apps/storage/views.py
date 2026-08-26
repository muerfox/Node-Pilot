from apps.common.viewsets import OrganizationScopedModelViewSet
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
