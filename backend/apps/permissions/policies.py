"""
Policy service: the single place authorization decisions get made. DRF
views never hardcode "if user.role == 'admin'" -- they declare a required
permission codename and call into `has_permission`.
"""
from __future__ import annotations

from django.core.cache import cache

CACHE_TTL_SECONDS = 30


def _cache_key(user_id: int, organization_id: int | None, project_id: int | None) -> str:
    return f"nodepilot:rbac:{user_id}:{organization_id}:{project_id}"


def _codenames_for(user, organization, project=None) -> frozenset[str]:
    from apps.permissions.models import RoleAssignment

    if organization is None:
        return frozenset()

    key = _cache_key(user.pk, organization.pk, project.pk if project else None)
    cached = cache.get(key)
    if cached is not None:
        return cached

    assignments = RoleAssignment.objects.filter(user=user, organization=organization).filter(
        models_q_project(project)
    )
    codenames: set[str] = set()
    for assignment in assignments.prefetch_related("role__permissions"):
        codenames.update(p.codename for p in assignment.role.permissions.all())

    result = frozenset(codenames)
    cache.set(key, result, CACHE_TTL_SECONDS)
    return result


def models_q_project(project):
    from django.db.models import Q

    if project is None:
        return Q(project__isnull=True)
    return Q(project__isnull=True) | Q(project=project)


def has_permission(user, organization, codename: str, project=None) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if organization is None:
        return False
    return codename in _codenames_for(user, organization, project)


def require_permission(user, organization, codename: str, project=None) -> None:
    from apps.common.exceptions import PermissionDeniedError

    if not has_permission(user, organization, codename, project=project):
        raise PermissionDeniedError(f"Missing required permission: {codename}")


def organizations_with_permission(user, codename: str, candidate_org_ids=None) -> set[int]:
    """
    Returns the subset of `candidate_org_ids` (default: every organization
    the user belongs to) in which the user holds `codename`. Used to
    permission-filter list endpoints instead of requiring every list call
    to specify a single `?organization=`.
    """
    from apps.organizations.models import Membership

    if candidate_org_ids is None:
        candidate_org_ids = list(Membership.objects.filter(user=user).values_list("organization_id", flat=True))

    if getattr(user, "is_superuser", False):
        return set(candidate_org_ids)

    from apps.organizations.models import Organization

    allowed = set()
    for org_id in candidate_org_ids:
        org = Organization(pk=org_id)  # avoid a query per id; has_permission only needs .pk
        if has_permission(user, org, codename):
            allowed.add(org_id)
    return allowed


def invalidate_cache_for(user_id: int) -> None:
    # Cache entries are namespaced by user/org/project; the TTL keeps
    # staleness bounded to CACHE_TTL_SECONDS even without explicit
    # invalidation, so this is a best-effort speed-up, not a correctness
    # requirement.
    pass
