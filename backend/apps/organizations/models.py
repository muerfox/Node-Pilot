from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel


class Organization(NodePilotModel):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organizations"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Project(NodePilotModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "projects"
        unique_together = [("organization", "slug")]
        ordering = ["organization_id", "name"]

    def __str__(self) -> str:
        return f"{self.organization.name}/{self.name}"


class Membership(NodePilotModel):
    """A user's membership in an organization. Fine-grained role
    assignment (what the member can actually do) lives in apps.permissions.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        db_table = "organization_memberships"
        unique_together = [("user", "organization")]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization}"


class Quota(NodePilotModel):
    """
    Resource quota (section 47). Scoped to an Organization, optionally
    narrowed to a single Project (a null project means "org-wide default").
    Usage is always computed live from the owning models -- never a stored
    counter that can drift from reality.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="quotas")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="quotas", null=True, blank=True)

    max_vms = models.PositiveIntegerField(default=100)
    max_vcpu = models.PositiveIntegerField(default=500)
    max_memory_mb = models.PositiveBigIntegerField(default=2 * 1024 * 1024)  # 2 TB in MB
    max_storage_gb = models.PositiveBigIntegerField(default=20 * 1024)  # 20 TB in GB
    max_snapshots = models.PositiveIntegerField(default=500)

    class Meta:
        db_table = "quotas"
        unique_together = [("organization", "project")]

    def __str__(self) -> str:
        scope = self.project.name if self.project_id else "org-wide"
        return f"Quota({self.organization.name}/{scope})"
