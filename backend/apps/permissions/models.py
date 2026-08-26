from django.conf import settings
from django.db import models

from apps.common.models import NodePilotModel
from apps.organizations.models import Organization, Project


class Permission(NodePilotModel):
    """A single grantable capability, e.g. "vm.start". Seeded from
    apps.permissions.catalog.PERMISSION_CATALOG."""

    codename = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "rbac_permissions"
        ordering = ["codename"]

    def __str__(self) -> str:
        return self.codename


class Role(NodePilotModel):
    """A named bundle of permissions. Organization-null roles are global
    templates (Admin/Operator/Viewer); an organization may also define its
    own custom roles."""

    name = models.CharField(max_length=100)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="roles", null=True, blank=True
    )
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        db_table = "rbac_roles"
        unique_together = [("organization", "name")]

    def __str__(self) -> str:
        return self.name


class RoleAssignment(NodePilotModel):
    """Grants a Role to a user, scoped to an organization and optionally
    narrowed to a single project within it."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="role_assignments")
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="role_assignments", null=True, blank=True
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="assignments")

    class Meta:
        db_table = "rbac_role_assignments"
        unique_together = [("user", "organization", "project", "role")]

    def __str__(self) -> str:
        scope = f"{self.organization}/{self.project}" if self.project_id else str(self.organization)
        return f"{self.user} -> {self.role} @ {scope}"
