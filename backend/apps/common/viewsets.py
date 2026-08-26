from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.common.permissions import HasResourcePermission


class OrganizationScopedQuerysetMixin:
    """
    Mixin for any resource that hangs off an Organization (directly or via
    `organization_field_path`, e.g. "node__organization"). Enforces RBAC
    via HasResourcePermission and restricts querysets to organizations the
    requesting user actually belongs to -- and, for `list`, further to
    organizations they hold the relevant permission in (detail actions are
    checked precisely via has_object_permission instead).
    """

    permission_classes = [IsAuthenticated, HasResourcePermission]
    permission_map: dict[str, str] = {}
    organization_field_path = "organization"
    lookup_field = "uuid"

    def get_organization(self):
        """
        Resolves the target organization for non-detail, non-list actions
        (chiefly `create`) from the request payload, generically walking
        `organization_field_path`. E.g. for a StoragePool
        (organization_field_path="node__organization"), the client submits
        a `node` uuid; this fetches that Node and returns its organization.
        Override in a subclass when the payload doesn't map directly
        (e.g. VirtualMachineViewSet resolves via `project`).
        """
        org_id = self.request.query_params.get("organization")
        if org_id:
            from apps.organizations.models import Organization

            return Organization.objects.filter(uuid=org_id).first()

        path_parts = self.organization_field_path.split("__")
        first_field = path_parts[0]

        if first_field == "organization" and len(path_parts) == 1:
            org_id = self.request.data.get("organization")
            if not org_id:
                return None
            from apps.organizations.models import Organization

            return Organization.objects.filter(uuid=org_id).first()

        related_id = self.request.data.get(first_field)
        if not related_id:
            return None
        model = self.get_queryset().model
        related_model = model._meta.get_field(first_field).related_model
        obj = related_model.objects.filter(uuid=related_id).first()
        if obj is None:
            return None
        for part in path_parts[1:]:
            obj = getattr(obj, part, None)
            if obj is None:
                return None
        return obj

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return queryset

        from apps.organizations.models import Membership

        org_ids = list(Membership.objects.filter(user=user).values_list("organization_id", flat=True))

        if getattr(self, "action", None) == "list":
            codename = self.permission_map.get("list") or getattr(self, "required_permission", None)
            if codename:
                from apps.permissions.policies import organizations_with_permission

                org_ids = list(organizations_with_permission(user, codename, org_ids))

        filter_kwargs = {f"{self.organization_field_path}_id__in": org_ids}
        return queryset.filter(**filter_kwargs)


class OrganizationScopedModelViewSet(OrganizationScopedQuerysetMixin, ModelViewSet):
    pass


class OrganizationScopedReadOnlyViewSet(OrganizationScopedQuerysetMixin, ReadOnlyModelViewSet):
    pass
