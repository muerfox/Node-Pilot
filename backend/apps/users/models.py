import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Extends Django's built-in auth user (section 2: use Django's built-in
    authentication/permissions) with the fields NodePilot needs: a stable
    public UUID and a flag for non-interactive service accounts used by
    automation/webhook integrations.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    is_service_account = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.username
