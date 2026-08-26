from rest_framework import serializers

from apps.organizations.models import Membership, Organization, Project, Quota


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["uuid", "name", "slug", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class ProjectSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Organization.objects.all())

    class Meta:
        model = Project
        fields = ["uuid", "organization", "name", "slug", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["uuid", "created_at", "updated_at"]


class MembershipSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Organization.objects.all())
    user = serializers.SlugRelatedField(slug_field="uuid", queryset=Membership._meta.get_field("user").related_model.objects.all())

    class Meta:
        model = Membership
        fields = ["uuid", "organization", "user", "created_at"]
        read_only_fields = ["uuid", "created_at"]


class QuotaSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=Organization.objects.all())
    project = serializers.SlugRelatedField(slug_field="uuid", queryset=Project.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Quota
        fields = ["uuid", "organization", "project", "max_vms", "max_vcpu", "max_memory_mb", "max_storage_gb", "max_snapshots"]
        read_only_fields = ["uuid"]
