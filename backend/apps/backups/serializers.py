from rest_framework import serializers

from apps.backups.models import Backup, BackupSchedule, BackupTarget
from apps.virtual_machines.models import VirtualMachine


class BackupTargetSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=BackupTarget._meta.get_field("organization").related_model.objects.all())

    class Meta:
        model = BackupTarget
        fields = ["uuid", "organization", "name", "type", "config", "encryption_key_id", "enabled", "created_at"]
        read_only_fields = ["uuid", "created_at"]


class BackupSerializer(serializers.ModelSerializer):
    vm = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine.objects.all())
    target = serializers.SlugRelatedField(slug_field="uuid", queryset=BackupTarget.objects.all())

    class Meta:
        model = Backup
        fields = ["uuid", "vm", "target", "type", "status", "size_bytes", "checksum", "encrypted", "started_at", "finished_at", "retention_expires_at", "created_at"]
        read_only_fields = ["uuid", "status", "size_bytes", "checksum", "started_at", "finished_at", "created_at"]


class BackupScheduleSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=BackupSchedule._meta.get_field("organization").related_model.objects.all())
    vm = serializers.SlugRelatedField(slug_field="uuid", queryset=VirtualMachine.objects.all())
    target = serializers.SlugRelatedField(slug_field="uuid", queryset=BackupTarget.objects.all())

    class Meta:
        model = BackupSchedule
        fields = ["uuid", "organization", "vm", "target", "backup_type", "cron_expression", "timezone", "retention_days", "enabled", "created_at"]
        read_only_fields = ["uuid", "created_at"]

    def validate_cron_expression(self, value: str) -> str:
        if len(value.split()) != 5:
            raise serializers.ValidationError("Expected a standard 5-field cron expression (minute hour day-of-month month day-of-week).")
        return value
