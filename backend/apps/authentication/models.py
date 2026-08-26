import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import NodePilotModel

TOKEN_PREFIX = "npt_"


class APIToken(NodePilotModel):
    """
    Long-lived API credential (section 32). The raw secret is shown to the
    user exactly once, at creation time; only its SHA-256 hash is ever
    persisted, matching "never store raw API tokens."
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    prefix = models.CharField(max_length=12, db_index=True, help_text="First few chars of the raw token, for identification in listings.")
    scopes = models.JSONField(default=list, blank=True, help_text="List of permission codenames this token is limited to, or [] for the user's full permission set.")
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_tokens"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix}...)"

    @property
    def is_valid(self) -> bool:
        if self.revoked:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    @staticmethod
    def generate() -> tuple[str, str, str]:
        """Returns (raw_token, token_hash, prefix)."""
        raw_secret = secrets.token_urlsafe(32)
        raw_token = f"{TOKEN_PREFIX}{raw_secret}"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return raw_token, token_hash, raw_token[: len(TOKEN_PREFIX) + 8]

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def mark_used(self) -> None:
        APIToken.objects.filter(pk=self.pk).update(last_used_at=timezone.now())

    def revoke(self) -> None:
        self.revoked = True
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked", "revoked_at"])
