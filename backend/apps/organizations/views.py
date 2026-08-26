from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.organizations.models import Membership, Organization, Project, Quota
from apps.organizations.serializers import MembershipSerializer, OrganizationSerializer, ProjectSerializer, QuotaSerializer


class OrganizationViewSet(OrganizationScopedModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    organization_field_path = "id"  # Organization *is* the scope; filtered by membership directly below.
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    search_fields = ["name", "slug"]

    def get_queryset(self):
        user = self.request.user
        qs = Organization.objects.all()
        if user.is_superuser:
            return qs
        return qs.filter(memberships__user=user).distinct()

    def get_organization(self):
        # An Organization *is* its own scope: for update/destroy, resolve
        # it straight from the URL rather than the (nonexistent) generic
        # "organization" field on the request body.
        uuid_value = self.kwargs.get(self.lookup_field)
        if not uuid_value:
            return None
        return Organization.objects.filter(uuid=uuid_value).first()


class ProjectViewSet(OrganizationScopedModelViewSet):
    queryset = Project.objects.select_related("organization").all()
    serializer_class = ProjectSerializer
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    search_fields = ["name", "slug"]
    filterset_fields = ["organization", "is_active"]


class MembershipViewSet(OrganizationScopedModelViewSet):
    queryset = Membership.objects.select_related("user", "organization").all()
    serializer_class = MembershipSerializer
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    filterset_fields = ["organization", "user"]


class QuotaViewSet(OrganizationScopedModelViewSet):
    queryset = Quota.objects.select_related("organization", "project").all()
    serializer_class = QuotaSerializer
    permission_map = {
        "list": "organization.manage",
        "retrieve": "organization.manage",
        "create": "organization.manage",
        "update": "organization.manage",
        "partial_update": "organization.manage",
        "destroy": "organization.manage",
    }
    filterset_fields = ["organization", "project"]
