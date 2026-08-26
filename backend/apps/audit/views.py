from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.common.permissions import HasResourcePermission
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


class AuditLogViewSet(ReadOnlyModelViewSet):
    """Read-only by design (section 30): audit entries can never be edited
    or removed through the API."""

    queryset = AuditLog.objects.select_related("actor", "organization").all()
    serializer_class = AuditLogSerializer
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated, HasResourcePermission]
    required_permission = "audit.view"
    filterset_fields = ["organization", "action", "resource_type", "result", "actor"]
    search_fields = ["action", "resource_type", "resource_id", "actor_label"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        from apps.organizations.models import Membership
        from apps.permissions.policies import organizations_with_permission

        org_ids = list(Membership.objects.filter(user=user).values_list("organization_id", flat=True))
        if self.action == "list":
            org_ids = list(organizations_with_permission(user, "audit.view", org_ids))
        return qs.filter(organization_id__in=org_ids)
