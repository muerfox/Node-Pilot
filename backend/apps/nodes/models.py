import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import NodePilotModel

AGENT_TOKEN_PREFIX = "npa_"


class NodeAdminState(models.TextChoices):
    """Administrator-controlled desired state. Combined with heartbeat
    freshness (never trusted alone) to compute Node.effective_status()."""

    ACTIVE = "ACTIVE", "Active"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    DISABLED = "DISABLED", "Disabled"


class NodeStatus(models.TextChoices):
    """Computed, user-facing status (section 8)."""

    ONLINE = "ONLINE", "Online"
    OFFLINE = "OFFLINE", "Offline"
    WARNING = "WARNING", "Warning"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    DISABLED = "DISABLED", "Disabled"


class AgentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"
    REVOKED = "REVOKED", "Revoked"
    OFFLINE = "OFFLINE", "Offline"


class Node(NodePilotModel):
    """A physical or virtual Linux KVM hypervisor (section 8)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="nodes")

    name = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255)
    fqdn = models.CharField(max_length=255, blank=True, default="")

    admin_state = models.CharField(max_length=20, choices=NodeAdminState.choices, default=NodeAdminState.ACTIVE)

    agent_version = models.CharField(max_length=32, blank=True, default="")
    kernel = models.CharField(max_length=128, blank=True, default="")
    architecture = models.CharField(max_length=32, blank=True, default="")
    cpu_model = models.CharField(max_length=255, blank=True, default="")
    cpu_threads = models.PositiveIntegerField(default=0)
    cpu_cores = models.PositiveIntegerField(default=0)
    cpu_sockets = models.PositiveIntegerField(default=0)

    memory_total_mb = models.PositiveBigIntegerField(default=0)
    memory_available_mb = models.PositiveBigIntegerField(default=0)
    storage_total_gb = models.PositiveBigIntegerField(default=0)
    storage_available_gb = models.PositiveBigIntegerField(default=0)

    reported_vm_count = models.PositiveIntegerField(default=0)
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "nodes"
        unique_together = [("organization", "hostname")]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def effective_status(self) -> str:
        """
        Never trust the DB alone (section 8): ONLINE/OFFLINE/WARNING are
        derived from `last_seen` freshness at read time, layered under the
        administrator's desired admin_state.
        """
        from django.conf import settings as django_settings

        if self.admin_state == NodeAdminState.DISABLED:
            return NodeStatus.DISABLED
        if self.admin_state == NodeAdminState.MAINTENANCE:
            return NodeStatus.MAINTENANCE

        threshold = django_settings.NODEPILOT["OFFLINE_THRESHOLD_SECONDS"]
        if self.last_seen is None:
            return NodeStatus.OFFLINE
        age = (timezone.now() - self.last_seen).total_seconds()
        if age > threshold:
            return NodeStatus.OFFLINE
        if age > threshold / 2:
            return NodeStatus.WARNING
        agent = getattr(self, "agent", None)
        if agent is not None and agent.status != AgentStatus.ACTIVE:
            return NodeStatus.WARNING
        return NodeStatus.ONLINE

    def is_schedulable(self) -> bool:
        return self.effective_status() == NodeStatus.ONLINE and self.admin_state == NodeAdminState.ACTIVE


class Agent(NodePilotModel):
    """
    Unique agent identity for a Node (section 4). The controller never
    needs unrestricted SSH access -- the agent authenticates outbound with
    this credential over the secure agent protocol (heartbeat HTTP calls
    and the persistent command WebSocket).
    """

    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="agent")
    agent_id = models.UUIDField(unique=True, default=None, null=True)
    status = models.CharField(max_length=20, choices=AgentStatus.choices, default=AgentStatus.ACTIVE)

    token_hash = models.CharField(max_length=64, unique=True, db_index=True, blank=True, default="")
    token_prefix = models.CharField(max_length=12, blank=True, default="")

    # mTLS architecture (section 4): certificate-based auth can be enabled
    # per-agent in addition to / instead of the bearer token.
    certificate_fingerprint = models.CharField(max_length=128, blank=True, default="")
    mtls_enabled = models.BooleanField(default=False)

    protocol_version = models.CharField(max_length=16, default="1.0")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agents"

    def __str__(self) -> str:
        return f"Agent({self.node.name})"

    @property
    def is_usable(self) -> bool:
        return self.status == AgentStatus.ACTIVE

    @staticmethod
    def generate_token() -> tuple[str, str, str]:
        raw_secret = secrets.token_urlsafe(32)
        raw_token = f"{AGENT_TOKEN_PREFIX}{raw_secret}"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return raw_token, token_hash, raw_token[: len(AGENT_TOKEN_PREFIX) + 8]

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def rotate_token(self) -> str:
        raw_token, token_hash, prefix = self.generate_token()
        self.token_hash = token_hash
        self.token_prefix = prefix
        self.save(update_fields=["token_hash", "token_prefix"])
        return raw_token

    def revoke(self) -> None:
        self.status = AgentStatus.REVOKED
        self.revoked_at = timezone.now()
        self.token_hash = ""
        self.save(update_fields=["status", "revoked_at", "token_hash"])
