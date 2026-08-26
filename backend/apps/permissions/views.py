from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.common.permissions import HasResourcePermission
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.permissions.models import Permission, Role, RoleAssignment
from apps.permissions.serializers import PermissionSerializer, RoleAssignmentSerializer, RoleSerializer


class PermissionViewSet(ReadOnlyModelViewSet):
    """Read-only: the permission catalog is fixed code, not user data.
    Any authenticated user may read it (needed to render role editors);
    it carries no per-organization data."""

    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    lookup_field = "codename"
    permission_classes = [IsAuthenticated]


class RoleViewSet(OrganizationScopedModelViewSet):
    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    organization_field_path = "organization"

    def get_queryset(self):
        # Include global system role templates (organization is null) plus
        # org-scoped roles for orgs the user belongs to.
        base = super().get_queryset()
        return base | Role.objects.filter(organization__isnull=True)


class RoleAssignmentViewSet(OrganizationScopedModelViewSet):
    queryset = RoleAssignment.objects.select_related("user", "organization", "project", "role").all()
    serializer_class = RoleAssignmentSerializer
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    filterset_fields = ["organization", "project", "user", "role"]
