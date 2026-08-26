from apps.common.viewsets import OrganizationScopedReadOnlyViewSet
from apps.events.models import Event
from apps.events.serializers import EventSerializer


class EventViewSet(OrganizationScopedReadOnlyViewSet):
    """Events are emitted internally (apps.events.services.emit_event),
    never created directly via the API."""

    queryset = Event.objects.select_related("organization", "actor").all()
    serializer_class = EventSerializer
    permission_map = {"list": "event.view", "retrieve": "event.view"}
    filterset_fields = ["type", "severity", "resource_type", "resource_id"]
    search_fields = ["type", "resource_type", "resource_id"]
    ordering_fields = ["created_at"]
