from rest_framework import serializers

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["uuid", "username", "email", "first_name", "last_name", "is_active", "is_service_account", "date_joined", "last_login"]
        read_only_fields = ["uuid", "date_joined", "last_login"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=12)

    class Meta:
        model = User
        fields = ["uuid", "username", "email", "first_name", "last_name", "password", "is_service_account"]
        read_only_fields = ["uuid"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
