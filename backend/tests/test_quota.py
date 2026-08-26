import pytest

from apps.common.exceptions import QuotaExceeded
from apps.organizations.models import Quota
from apps.organizations.services import assert_quota_available, current_usage
from apps.virtual_machines.models import VirtualMachine

pytestmark = pytest.mark.django_db


def _make_vm(organization, project, *, cpu=2, memory_mb=2048, name="vm"):
    return VirtualMachine.objects.create(
        organization=organization, project=project, name=name, cpu_count=cpu, memory_mb=memory_mb, status="STOPPED",
    )


def test_no_quota_configured_is_unrestricted(organization, project):
    assert_quota_available(organization, project, additional_vms=1000)  # should not raise


def test_quota_blocks_over_limit_request(organization, project):
    Quota.objects.create(organization=organization, max_vms=1, max_vcpu=2, max_memory_mb=4096, max_storage_gb=100, max_snapshots=5)
    _make_vm(organization, project)  # consumes the one allowed VM

    with pytest.raises(QuotaExceeded):
        assert_quota_available(organization, project, additional_vms=1)


def test_quota_allows_within_limit(organization, project):
    Quota.objects.create(organization=organization, max_vms=5, max_vcpu=20, max_memory_mb=40960, max_storage_gb=1000, max_snapshots=50)
    _make_vm(organization, project)
    assert_quota_available(organization, project, additional_vms=1)  # 2 total, still under 5


def test_current_usage_aggregates_existing_vms(organization, project):
    _make_vm(organization, project, cpu=2, memory_mb=1024, name="a")
    _make_vm(organization, project, cpu=4, memory_mb=2048, name="b")

    usage = current_usage(organization, project)
    assert usage.vms == 2
    assert usage.vcpu == 6
    assert usage.memory_mb == 3072


def test_org_level_quota_applies_when_no_project_specific_quota(organization, project):
    Quota.objects.create(organization=organization, project=None, max_vms=1, max_vcpu=100, max_memory_mb=100000, max_storage_gb=10000, max_snapshots=100)
    _make_vm(organization, project)
    with pytest.raises(QuotaExceeded):
        assert_quota_available(organization, project, additional_vms=1)
