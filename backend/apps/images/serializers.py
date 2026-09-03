from rest_framework import serializers

from apps.images.models import Image, ImageUploadSession
from apps.storage.models import StoragePool


class ImageSerializer(serializers.ModelSerializer):
    storage = serializers.SlugRelatedField(slug_field="uuid", read_only=True)

    class Meta:
        model = Image
        # `storage` is declared above as a SlugRelatedField (read-only,
        # UUID) precisely so image list/retrieve responses show which
        # pool it lives on -- it must actually be listed here too, or
        # DRF's own ModelSerializer field-name assertion fires on every
        # serialization attempt: any declared field not also present in
        # Meta.fields is a hard error, not silently dropped.
        fields = ["uuid", "name", "version", "type", "format", "storage", "size_bytes", "checksum_algorithm", "sha256", "source", "status", "metadata", "created_at"]
        read_only_fields = ["uuid", "size_bytes", "sha256", "status", "created_at"]


class InitiateUploadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    version = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    type = serializers.ChoiceField(choices=["ISO", "QCOW2", "RAW", "VMDK"])
    format = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    storage = serializers.SlugRelatedField(slug_field="uuid", queryset=StoragePool.objects.all())
    total_size_bytes = serializers.IntegerField(min_value=1)
    expected_sha256 = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class ImageUploadSessionSerializer(serializers.ModelSerializer):
    image = ImageSerializer(read_only=True)

    class Meta:
        model = ImageUploadSession
        fields = ["uuid", "image", "total_size_bytes", "received_bytes", "next_chunk_index", "status", "error"]
        read_only_fields = fields
