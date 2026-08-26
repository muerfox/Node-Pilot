from rest_framework import serializers

from apps.authentication.models import APIToken


class APITokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIToken
        fields = ["uuid", "name", "prefix", "scopes", "expires_at", "last_used_at", "revoked", "created_at"]
        read_only_fields = ["uuid", "prefix", "last_used_at", "revoked", "created_at"]


class APITokenCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIToken
        fields = ["uuid", "name", "scopes", "expires_at"]
        read_only_fields = ["uuid"]

    def validate_scopes(self, value):
        if value:
            from apps.permissions.catalog import PERMISSION_CATALOG

            unknown = set(value) - set(PERMISSION_CATALOG)
            if unknown:
                raise serializers.ValidationError(f"Unknown permission codenames: {sorted(unknown)}")
        return value
