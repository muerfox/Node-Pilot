"""
Reusable RBAC enforcement (section 7): authorization checks must not be
hardcoded per-view. Views instead declare `required_permission` (a single
codename, e.g. "vm.view") or `permission_map` (per-action codenames) and
this permission class asks the permissions app's policy service whether
the requesting user holds that permission within the resolved organization.

Three cases, because "the organization" means something different
depending on whether an object exists yet:

  * Detail actions (retrieve/update/destroy/detail=True custom actions):
    there's no reliable way to know the organization before fetching the
    object, so `has_permission` defers (returns True) and the real check
    happens in `has_object_permission` once DRF has the instance.
  * "list": there's no single object either, and requiring an
    `?organization=` filter would be a usability regression. Defers to the
    viewset's queryset, which (via OrganizationScopedQuerysetMixin) must
    restrict rows to organizations the user actually holds the permission
    in -- see apps.permissions.policies.organizations_with_permission.
  * Everything else (create, and non-detail custom actions): the
    organization must be resolvable *before* the view body runs, via
    `view.get_organization()`.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class HasResourcePermission(BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        codename = self._resolve_codename(view)
        if codename is None:
            return False  # View didn't declare a requirement; fail closed.

        if getattr(view, "detail", False):
            return True  # Deferred to has_object_permission.
        if getattr(view, "action", None) == "list":
            return True  # Deferred to queryset filtering.

        organization = self._resolve_organization(request, view)
        from apps.permissions.policies import has_permission

        # `has_permission` itself denies a None organization for anyone but
        # a superuser (who needs no organization context at all, e.g. to
        # create a brand-new Organization or a global Role template).
        return has_permission(request.user, organization, codename)

    def has_object_permission(self, request, view, obj) -> bool:
        codename = self._resolve_codename(view)
        if codename is None:
            return False
        organization = getattr(obj, "organization", None) or self._resolve_organization(request, view)
        from apps.permissions.policies import has_permission

        return has_permission(request.user, organization, codename)

    @staticmethod
    def _resolve_codename(view) -> str | None:
        permission_map = getattr(view, "permission_map", None)
        if permission_map:
            return permission_map.get(view.action)
        return getattr(view, "required_permission", None)

    @staticmethod
    def _resolve_organization(request, view):
        if hasattr(view, "get_organization"):
            return view.get_organization()
        org_id = request.query_params.get("organization") or request.data.get("organization")
        if not org_id:
            return None
        from apps.organizations.models import Organization

        return Organization.objects.filter(uuid=org_id).first()
