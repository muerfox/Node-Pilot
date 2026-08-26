from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasResourcePermission
from apps.metrics.store import get_node_samples, get_vm_samples


class NodeMetricsView(APIView):
    permission_classes = [IsAuthenticated, HasResourcePermission]
    required_permission = "node.view"

    def get_organization(self):
        node = self._get_node()
        return node.organization if node else None

    def _get_node(self):
        from apps.nodes.models import Node

        return Node.objects.filter(uuid=self.kwargs["uuid"]).select_related("organization").first()

    def get(self, request, uuid):
        node = self._get_node()
        if node is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "Node not found.", "details": {}}}, status=404)
        since = request.query_params.get("since_seconds")
        samples = get_node_samples(node, int(since) if since else None)
        return Response({"node": str(node.uuid), "samples": samples})


class VMMetricsView(APIView):
    permission_classes = [IsAuthenticated, HasResourcePermission]
    required_permission = "vm.view"

    def get_organization(self):
        vm = self._get_vm()
        return vm.organization if vm else None

    def _get_vm(self):
        from apps.virtual_machines.models import VirtualMachine

        return VirtualMachine.objects.filter(uuid=self.kwargs["uuid"]).select_related("organization").first()

    def get(self, request, uuid):
        vm = self._get_vm()
        if vm is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "VM not found.", "details": {}}}, status=404)
        since = request.query_params.get("since_seconds")
        samples = get_vm_samples(vm, int(since) if since else None)
        return Response({"vm": str(vm.uuid), "samples": samples})
