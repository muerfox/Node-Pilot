import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Adds created_at/updated_at. Every domain model should inherit this."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDPublicIDModel(models.Model):
    """
    Internal primary keys stay integer (fast FKs, small indexes); the `uuid`
    field is the externally visible identifier used in the API and by the
    agent protocol, per the "UUIDs for public resource identifiers" rule.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class NodePilotModel(TimeStampedModel, UUIDPublicIDModel):
    class Meta:
        abstract = True
