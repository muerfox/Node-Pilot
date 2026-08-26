"""
Quota enforcement (section 47). Must be checked transactionally before
provisioning -- callers should hold a `select_for_update()` on the Quota
row (see `locked_quota_for`) for the duration of the check + the write
that consumes the quota, so two concurrent VM creations can't both pass
the check and jointly exceed the limit.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.common.exceptions import QuotaExceeded
from apps.organizations.models import Organization, Project, Quota


@dataclass
class QuotaUsage:
    vms: int
    vcpu: int
    memory_mb: int
    storage_gb: int
    snapshots: int


def _effective_quota(organization: Organization, project: Project | None) -> Quota | None:
    if project is not None:
        scoped = Quota.objects.filter(organization=organization, project=project).first()
        if scoped:
            return scoped
    return Quota.objects.filter(organization=organization, project__isnull=True).first()


def locked_quota_for(organization: Organization, project: Project | None) -> Quota | None:
    """Must be called inside an active transaction."""
    quota = _effective_quota(organization, project)
    if quota is None:
        return None
    return Quota.objects.select_for_update().get(pk=quota.pk)


def current_usage(organization: Organization, project: Project | None) -> QuotaUsage:
    # Local import: virtual_machines depends on organizations, not the reverse.
    from apps.virtual_machines.models import VirtualMachine

    qs = VirtualMachine.objects.filter(organization=organization).exclude(status="DELETING")
    if project is not None:
        qs = qs.filter(project=project)

    vcpu_total = 0
    memory_total = 0
    storage_total_bytes = 0
    snapshot_total = 0
    vm_count = 0
    for vm in qs.prefetch_related("disks", "snapshots"):
        vm_count += 1
        vcpu_total += vm.cpu_count
        memory_total += vm.memory_mb
        storage_total_bytes += sum(disk.size_bytes for disk in vm.disks.all())
        snapshot_total += vm.snapshots.count()

    return QuotaUsage(
        vms=vm_count,
        vcpu=vcpu_total,
        memory_mb=memory_total,
        storage_gb=storage_total_bytes // (1024**3),
        snapshots=snapshot_total,
    )


def assert_quota_available(
    organization: Organization,
    project: Project | None,
    *,
    additional_vms: int = 0,
    additional_vcpu: int = 0,
    additional_memory_mb: int = 0,
    additional_storage_gb: int = 0,
    additional_snapshots: int = 0,
) -> None:
    """Raises QuotaExceeded if provisioning the additional resources would
    breach the organization/project quota. Call within a transaction that
    also holds `locked_quota_for` to avoid TOCTOU races."""
    quota = _effective_quota(organization, project)
    if quota is None:
        return  # No quota configured: unrestricted.

    usage = current_usage(organization, project)
    checks = [
        ("max_vms", usage.vms + additional_vms, "VMs"),
        ("max_vcpu", usage.vcpu + additional_vcpu, "vCPUs"),
        ("max_memory_mb", usage.memory_mb + additional_memory_mb, "MB of memory"),
        ("max_storage_gb", usage.storage_gb + additional_storage_gb, "GB of storage"),
        ("max_snapshots", usage.snapshots + additional_snapshots, "snapshots"),
    ]
    for field, projected, label in checks:
        limit = getattr(quota, field)
        if projected > limit:
            raise QuotaExceeded(
                f"This operation would use {projected} {label}, exceeding the quota of {limit}.",
                details={"field": field, "limit": limit, "projected": projected},
            )


@transaction.atomic
def check_and_reserve(organization: Organization, project: Project | None, **additional) -> None:
    """Locks the quota row and re-validates within the same transaction as
    the caller's resource creation, so the whole thing is atomic."""
    locked_quota_for(organization, project)
    assert_quota_available(organization, project, **additional)
