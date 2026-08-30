from django.core.exceptions import ValidationError as DjangoValidationError
from django_celery_beat.validators import (
    day_of_month_validator,
    day_of_week_validator,
    hour_validator,
    minute_validator,
    month_of_year_validator,
)
from rest_framework import serializers

from apps.backups.models import Backup, BackupSchedule, BackupTarget
from apps.virtual_machines.models import VirtualMachine

# Same order as the 5 cron fields and django_celery_beat's own
# CrontabSchedule field validators -- reusing them (rather than writing
# a second, possibly-diverging cron parser) guarantees that anything
# this accepts is exactly what _sync_periodic_task's CrontabSchedule
# will also accept, so a schedule can't be created here and then
# silently fail to ever actually run under Celery Beat.
_CRON_FIELD_VALIDATORS = [minute_validator, hour_validator, day_of_month_validator, month_of_year_validator, day_of_week_validator]
_CRON_FIELD_NAMES = ["minute", "hour", "day-of-month", "month", "day-of-week"]

# Keys within BackupTarget.config that hold a real credential rather than
# connection metadata (bucket/endpoint_url/region/prefix/path are fine to
# show back). Now that S3/MinIO/Ceph targets carry a real access-key pair
# here, this needs the same "not re-exposed on every GET" treatment
# apps.webhooks.serializers already gives Webhook.secret.
_SENSITIVE_CONFIG_KEYS = {"secret_access_key", "access_key_id"}


def _mask_config(config: dict) -> dict:
    masked = dict(config)
    for key in _SENSITIVE_CONFIG_KEYS:
        value = masked.get(key)
        if value:
            masked[key] = f"{'*' * 8}{value[-4:]}" if len(value) > 4 else "*" * 8
    return masked


class BackupTargetSerializer(serializers.ModelSerializer):
    """Used for list/retrieve/update -- masks credential-shaped config
    keys. See BackupTargetCreateSerializer for the one place the full
    config (as submitted) is echoed back."""

    organization = serializers.SlugRelatedField(slug_field="uuid", queryset=BackupTarget._meta.get_field("organization").related_model.objects.all())
    config = serializers.SerializerMethodField()

    class Meta:
        model = BackupTarget
        fields = ["uuid", "organization", "name", "type", "config", "encryption_key_id", "enabled", "created_at"]
        read_only_fields = ["uuid", "config", "created_at"]

    def get_config(self, obj: BackupTarget) -> dict:
        return _mask_config(obj.config)


class BackupTargetCreateSerializer(BackupTargetSerializer):
    """Full, unmasked config -- both on the way in (this is how
    credentials actually get set) and in this specific response, once,
    the same pattern APIToken/Webhook use for their own secrets."""

    config = serializers.JSONField()

    class Meta(BackupTargetSerializer.Meta):
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
        fields = value.split()
        if len(fields) != 5:
            raise serializers.ValidationError("Expected a standard 5-field cron expression (minute hour day-of-month month day-of-week).")
        for field, name, validator in zip(fields, _CRON_FIELD_NAMES, _CRON_FIELD_VALIDATORS):
            try:
                validator(field)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(f"Invalid {name} field {field!r}: {exc}") from exc
        return value
