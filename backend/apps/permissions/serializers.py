from rest_framework import serializers

from apps.permissions.models import Permission, Role, RoleAssignment


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["uuid", "codename", "description"]
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(
        slug_field="uuid", queryset=Role._meta.get_field("organization").related_model.objects.all(), required=False, allow_null=True
    )
    permissions = serializers.SlugRelatedField(slug_field="codename", queryset=Permission.objects.all(), many=True)

    class Meta:
        model = Role
        fields = ["uuid", "name", "organization", "permissions", "is_system"]
        read_only_fields = ["uuid", "is_system"]


class RoleAssignmentSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(
        slug_field="uuid", queryset=RoleAssignment._meta.get_field("organization").related_model.objects.all()
    )
    project = serializers.SlugRelatedField(
        slug_field="uuid",
        queryset=RoleAssignment._meta.get_field("project").related_model.objects.all(),
        required=False,
        allow_null=True,
    )
    user = serializers.SlugRelatedField(slug_field="uuid", queryset=RoleAssignment._meta.get_field("user").related_model.objects.all())
    role = serializers.SlugRelatedField(slug_field="uuid", queryset=Role.objects.all())

    class Meta:
        model = RoleAssignment
        fields = ["uuid", "user", "organization", "project", "role", "created_at"]
        read_only_fields = ["uuid", "created_at"]
