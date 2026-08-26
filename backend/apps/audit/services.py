from __future__ import annotations

from apps.audit.models import AuditLog, AuditResult


def log_action(
    *,
    actor=None,
    action: str,
    resource_type: str,
    resource_id: str = "",
    organization=None,
    ip_address: str | None = None,
    result: str = AuditResult.SUCCESS,
    metadata: dict | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        actor_label=getattr(actor, "username", "system"),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        organization=organization,
        ip_address=ip_address,
        result=result,
        metadata=metadata or {},
    )


def log_from_request(request, *, action: str, resource_type: str, resource_id: str = "", organization=None, result: str = AuditResult.SUCCESS, metadata: dict | None = None) -> AuditLog:
    actor = getattr(request, "user", None)
    if actor is not None and not actor.is_authenticated:
        actor = None
    return log_action(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        organization=organization,
        ip_address=_client_ip(request),
        result=result,
        metadata=metadata,
    )


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
