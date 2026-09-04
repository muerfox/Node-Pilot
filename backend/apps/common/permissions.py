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

Independent of all three: if the request was authenticated via a scoped
`APIToken` (apps.authentication.auth.APITokenAuthentication sets
`request.api_token`), the required codename must also be in that token's
own `scopes` list. This runs before anything else below -- a token
scoped to e.g. `["vm.view"]` must never be able to reach `vm.delete`
just because the user who created it could, regardless of which
organization or object is involved. An empty `scopes` list means
"this token carries the user's full permission set" (unscoped), matching
APIToken.scopes's own documented default.
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
        if not self._token_permits(request, codename):
            return False

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
        if not self._token_permits(request, codename):
            return False
        organization = self._resolve_organization_from_object(view, obj)
        from apps.permissions.policies import has_permission

        return has_permission(request.user, organization, codename)

    @staticmethod
    def _token_permits(request, codename: str) -> bool:
        token = getattr(request, "api_token", None)
        if token is None or not token.scopes:
            return True  # A JWT/session request, or an unscoped (full-access) token.
        return codename in token.scopes

    @staticmethod
    def _resolve_codename(view) -> str | None:
        permission_map = getattr(view, "permission_map", None)
        if permission_map:
            return permission_map.get(view.action)
        return getattr(view, "required_permission", None)

    @staticmethod
    def _resolve_organization_from_object(view, obj):
        """
        Derived strictly from the object already in hand -- walking
        `view.organization_field_path` (default "organization") against
        `obj` itself -- and NEVER from client-supplied query params or
        request body. Object-level checks used to fall back to
        `?organization=<uuid>` when `obj` had no direct `organization`
        field (true of StoragePool, Network, Subnet, IPAddress, IPPool,
        Snapshot, Backup, ...), which let an authenticated member of org
        A "borrow" a permission grant they hold in an unrelated org B by
        passing `?organization=<org-B-uuid>` on a request targeting an
        object that actually belongs to org A -- a cross-tenant IDOR.
        """
        path = getattr(view, "organization_field_path", "organization")
        target = obj
        for part in path.split("__"):
            target = getattr(target, part, None)
            if target is None:
                return None
        return target

    @staticmethod
    def _resolve_organization(request, view):
        if hasattr(view, "get_organization"):
            return view.get_organization()
        org_id = request.query_params.get("organization") or request.data.get("organization")
        if not org_id:
            return None
        from apps.organizations.models import Organization

        return Organization.objects.filter(uuid=org_id).first()
