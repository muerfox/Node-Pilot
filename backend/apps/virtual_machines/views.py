from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.virtual_machines import services
from apps.virtual_machines.models import VirtualMachine
from apps.virtual_machines.serializers import VirtualMachineCreateSerializer, VirtualMachineSerializer


class VirtualMachineViewSet(OrganizationScopedModelViewSet):
    """
    Every mutating action here returns {"job_id", "status": "queued"} per
    section 18 -- none of them perform virtualization work inline. Actual
    provisioning/lifecycle work happens in apps.virtual_machines.tasks via
    Celery, driven by apps.virtual_machines.services.
    """

    queryset = VirtualMachine.objects.select_related("organization", "project", "node").prefetch_related("disks", "nics").all()
    serializer_class = VirtualMachineSerializer
    permission_map = {
        "list": "vm.view",
        "retrieve": "vm.view",
        "create": "vm.create",
        "update": "vm.update",
        "partial_update": "vm.update",
        "destroy": "vm.delete",
        "start": "vm.start",
        "stop": "vm.stop",
        "reboot": "vm.reboot",
        "pause": "vm.stop",
        "resume": "vm.start",
        "clone": "vm.clone",
        "migrate": "vm.migrate",
        "console": "vm.console",
    }
    filterset_fields = ["status", "node", "project"]
    search_fields = ["name", "hostname", "description"]

    def get_organization(self):
        # Creation is scoped by `project`, not a top-level `organization`
        # field -- resolve it from there.
        project_id = self.request.data.get("project")
        if not project_id:
            return None
        from apps.organizations.models import Project

        project = Project.objects.filter(uuid=project_id).select_related("organization").first()
        return project.organization if project else None

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "vm_create"
            return [ScopedRateThrottle()]
        if self.action == "console":
            self.throttle_scope = "console_auth"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        serializer = VirtualMachineCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project = data["project"]

        disks = [
            {
                "storage": d["storage"], "name": d.get("name", ""), "size_bytes": d["size_gb"] * 1024**3,
                "bus": d["bus"], "bootable": d["bootable"], "format": d["format"],
            }
            for d in data.get("disks", [])
        ]
        nics = [
            {"network": n["network"], "model": n["model"], "vlan": n.get("vlan"), "mac_address": n.get("mac_address") or None, "bootable": n["bootable"]}
            for n in data.get("nics", [])
        ]

        vm, job = services.create_vm(
            organization=project.organization, project=project, name=data["name"], created_by=request.user,
            node=data.get("node"), template=data.get("template"), cpu_count=data["cpu_count"], memory_mb=data["memory_mb"],
            disks=disks, nics=nics, os_type=data["os_type"], firmware=data["firmware"],
            cloud_init_enabled=data["cloud_init_enabled"], cloud_init_config=data.get("cloud_init_config"),
            autostart=data["autostart"], idempotency_key=request.META.get("HTTP_IDEMPOTENCY_KEY", ""),
        )
        log_from_request(request, action="VM_CREATE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"id": str(vm.uuid), "status": vm.status, "job_id": str(job.uuid) if job else None}, status=status.HTTP_201_CREATED)

    def _job_response(self, request, job, *, audit_action: str, vm) -> Response:
        log_from_request(request, action=audit_action, resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def start(self, request, uuid=None):
        vm = self.get_object()
        job = services.start_vm(vm, request.user)
        return self._job_response(request, job, audit_action="VM_START", vm=vm)

    @action(detail=True, methods=["post"])
    def stop(self, request, uuid=None):
        vm = self.get_object()
        job = services.stop_vm(vm, request.user, force=bool(request.data.get("force", False)))
        return self._job_response(request, job, audit_action="VM_STOP", vm=vm)

    @action(detail=True, methods=["post"])
    def reboot(self, request, uuid=None):
        vm = self.get_object()
        job = services.reboot_vm(vm, request.user, force=bool(request.data.get("force", False)))
        return self._job_response(request, job, audit_action="VM_REBOOT", vm=vm)

    @action(detail=True, methods=["post"])
    def pause(self, request, uuid=None):
        vm = self.get_object()
        job = services.pause_vm(vm, request.user)
        return self._job_response(request, job, audit_action="VM_PAUSE", vm=vm)

    @action(detail=True, methods=["post"])
    def resume(self, request, uuid=None):
        vm = self.get_object()
        job = services.resume_vm(vm, request.user)
        return self._job_response(request, job, audit_action="VM_RESUME", vm=vm)

    def destroy(self, request, *args, **kwargs):
        vm = self.get_object()
        job = services.delete_vm(vm, request.user)
        log_from_request(request, action="VM_DELETE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def clone(self, request, uuid=None):
        vm = self.get_object()
        new_name = request.data.get("name")
        if not new_name:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "name is required", "details": {}}}, status=400)
        job = services.clone_vm(vm, request.user, new_name=new_name, linked=bool(request.data.get("linked", False)))
        return self._job_response(request, job, audit_action="VM_CLONE", vm=vm)

    @action(detail=True, methods=["post"])
    def migrate(self, request, uuid=None):
        vm = self.get_object()
        from apps.nodes.models import Node

        target_node = Node.objects.filter(uuid=request.data.get("target_node")).first()
        if target_node is None:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "target_node not found", "details": {}}}, status=400)
        services.migrate_vm(vm, request.user, target_node=target_node)  # raises 501 today; kept for a future release.
        return Response(status=status.HTTP_202_ACCEPTED)  # pragma: no cover - unreachable until migration ships

    @action(detail=True, methods=["get"])
    def console(self, request, uuid=None):
        vm = self.get_object()
        return Response(
            {
                "websocket_url": f"/ws/console/{vm.uuid}",
                "protocol": "nodepilot-console-v1",
                "note": "Connect using the browser session established at login; the relay opens the console on the agent for the duration of the connection.",
            }
        )
