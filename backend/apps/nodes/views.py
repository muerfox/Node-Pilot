from __future__ import annotations

import uuid as uuid_lib

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.nodes.auth import AgentTokenAuthentication
from apps.nodes.models import Agent, AgentStatus, Node, NodeAdminState
from apps.nodes.serializers import HeartbeatSerializer, NodeCreateSerializer, NodeSerializer
from apps.nodes.services import record_heartbeat


class IsAgent(BasePermission):
    def has_permission(self, request, view) -> bool:
        return getattr(request, "agent", None) is not None


class NodeViewSet(OrganizationScopedModelViewSet):
    queryset = Node.objects.select_related("organization", "agent").all()
    serializer_class = NodeSerializer
    permission_map = {
        "list": "node.view",
        "retrieve": "node.view",
        "create": "node.manage",
        "update": "node.manage",
        "partial_update": "node.manage",
        "destroy": "node.manage",
        "maintenance": "node.manage",
        "register_agent": "node.manage",
        "revoke_agent": "node.manage",
    }
    filterset_fields = ["organization", "admin_state"]
    search_fields = ["name", "hostname", "fqdn"]

    def get_serializer_class(self):
        if self.action == "create":
            return NodeCreateSerializer
        return NodeSerializer

    def perform_create(self, serializer):
        node = serializer.save()
        log_from_request(self.request, action="NODE_CREATE", resource_type="Node", resource_id=str(node.uuid), organization=node.organization)

    @action(detail=True, methods=["post"])
    def maintenance(self, request, uuid=None):
        node = self.get_object()
        enabled = bool(request.data.get("enabled", True))
        node.admin_state = NodeAdminState.MAINTENANCE if enabled else NodeAdminState.ACTIVE
        node.save(update_fields=["admin_state"])
        log_from_request(
            request, action="NODE_MAINTENANCE_TOGGLE", resource_type="Node", resource_id=str(node.uuid),
            organization=node.organization, metadata={"enabled": enabled},
        )
        return Response(NodeSerializer(node).data)

    @action(detail=True, methods=["post"], url_path="register-agent")
    def register_agent(self, request, uuid=None):
        """Issues (or re-issues) the agent credential for this node. The
        raw token is only ever returned here, once."""
        node = self.get_object()
        agent, _ = Agent.objects.get_or_create(node=node, defaults={"agent_id": uuid_lib.uuid4()})
        if agent.agent_id is None:
            agent.agent_id = uuid_lib.uuid4()
        agent.status = AgentStatus.ACTIVE
        raw_token = agent.rotate_token()
        log_from_request(request, action="AGENT_REGISTER", resource_type="Node", resource_id=str(node.uuid), organization=node.organization)
        return Response(
            {
                "node_id": str(node.uuid),
                "agent_id": str(agent.agent_id),
                "token": raw_token,
                "controller_version": settings.NODEPILOT["CONTROLLER_VERSION"],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="revoke-agent")
    def revoke_agent(self, request, uuid=None):
        node = self.get_object()
        agent = getattr(node, "agent", None)
        if agent is None:
            return Response({"detail": "No agent registered for this node."}, status=status.HTTP_404_NOT_FOUND)
        agent.revoke()
        log_from_request(request, action="AGENT_REVOKE", resource_type="Node", resource_id=str(node.uuid), organization=node.organization)
        return Response(NodeSerializer(node).data)


class HeartbeatView(APIView):
    """
    POST /api/v1/agent/heartbeat/  (Authorization: Agent <token>)

    Ingests a periodic heartbeat from a NodePilot Agent (section 53). This
    is the *only* write path an agent uses to push host state -- it never
    receives inbound shell access from the controller.
    """

    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAgent]
    throttle_classes = []

    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        node = record_heartbeat(request.agent, serializer.validated_data)
        return Response({"status": "ok", "node_status": node.effective_status()})
