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
        "attach_disk": "vm.update",
        "resize_disk": "vm.update",
        "remove_disk": "vm.update",
        "attach_nic": "vm.update",
        "remove_nic": "vm.update",
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
                "readonly": d["readonly"], "discard": d["discard"], "iothread": d["iothread"],
            }
            for d in data.get("disks", [])
        ]
        nics = [
            {
                "network": n["network"], "model": n["model"], "vlan": n.get("vlan"), "mac_address": n.get("mac_address") or None,
                "bootable": n["bootable"], "rate_limit_mbps": n.get("rate_limit_mbps"),
            }
            for n in data.get("nics", [])
        ]

        vm, job = services.create_vm(
            organization=project.organization, project=project, name=data["name"], created_by=request.user,
            node=data.get("node"), template=data.get("template"), cpu_count=data["cpu_count"], memory_mb=data["memory_mb"],
            disks=disks, nics=nics, os_type=data["os_type"], firmware=data["firmware"],
            boot_order=data.get("boot_order"), ballooning_enabled=data["ballooning_enabled"],
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

    @action(detail=True, methods=["post"], url_path="disks")
    def attach_disk(self, request, uuid=None):
        from apps.storage.models import StoragePool

        vm = self.get_object()
        storage = StoragePool.objects.filter(uuid=request.data.get("storage")).first()
        if storage is None:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "storage not found", "details": {}}}, status=400)
        size_gb = int(request.data.get("size_gb", 0))
        if size_gb <= 0:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "size_gb must be positive", "details": {}}}, status=400)
        disk, job = services.attach_disk(vm, storage=storage, size_gb=size_gb, bus=request.data.get("bus", "VIRTIO"), requested_by=request.user)
        log_from_request(request, action="VM_DISK_ATTACH", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"disk_id": str(disk.uuid), "job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path=r"disks/(?P<disk_uuid>[0-9a-f-]{36})/resize")
    def resize_disk(self, request, uuid=None, disk_uuid=None):
        vm = self.get_object()
        disk = vm.disks.filter(uuid=disk_uuid).first()
        if disk is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "disk not found", "details": {}}}, status=404)
        new_size_gb = int(request.data.get("size_gb", 0))
        job = services.resize_disk(vm, disk, new_size_gb, request.user)
        log_from_request(request, action="VM_DISK_RESIZE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["delete"], url_path=r"disks/(?P<disk_uuid>[0-9a-f-]{36})")
    def remove_disk(self, request, uuid=None, disk_uuid=None):
        vm = self.get_object()
        disk = vm.disks.filter(uuid=disk_uuid).first()
        if disk is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "disk not found", "details": {}}}, status=404)
        job = services.detach_disk(vm, disk, request.user)
        log_from_request(request, action="VM_DISK_DETACH", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="nics")
    def attach_nic(self, request, uuid=None):
        from apps.networks.models import Network

        vm = self.get_object()
        network = Network.objects.filter(uuid=request.data.get("network")).first()
        if network is None:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "network not found", "details": {}}}, status=400)
        nic, job = services.attach_nic(
            vm, network=network, model=request.data.get("model", "VIRTIO"), vlan=request.data.get("vlan"),
            rate_limit_mbps=request.data.get("rate_limit_mbps"), requested_by=request.user,
        )
        log_from_request(request, action="VM_NIC_ATTACH", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"nic_id": str(nic.uuid), "job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["delete"], url_path=r"nics/(?P<nic_uuid>[0-9a-f-]{36})")
    def remove_nic(self, request, uuid=None, nic_uuid=None):
        vm = self.get_object()
        nic = vm.nics.filter(uuid=nic_uuid).first()
        if nic is None:
            return Response({"error": {"code": "NOT_FOUND", "message": "nic not found", "details": {}}}, status=404)
        job = services.detach_nic(vm, nic, request.user)
        log_from_request(request, action="VM_NIC_DETACH", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"job_id": str(job.uuid), "status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"])
    def console(self, request, uuid=None):
        vm = self.get_object()
        return Response(
            {
                "websocket_url": f"/ws/console/{vm.uuid}",
                "protocol": "nodepilot-console-v1",
                "note": "Append ?token=<jwt-access-token> to the websocket URL (see apps.authentication.ws_auth); the relay opens the console on the agent for the duration of the connection.",
            }
        )
