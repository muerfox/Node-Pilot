from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import log_from_request
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.vm_templates.models import Template
from apps.vm_templates.serializers import DeployTemplateSerializer, TemplateSerializer
from apps.vm_templates.services import create_vm_from_template


class TemplateViewSet(OrganizationScopedModelViewSet):
    queryset = Template.objects.select_related("organization", "image").all()
    serializer_class = TemplateSerializer
    permission_map = {
        "list": "template.view", "retrieve": "template.view", "create": "template.manage",
        "update": "template.manage", "partial_update": "template.manage", "destroy": "template.manage",
        "deploy": "vm.create",
    }
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]

    @action(detail=True, methods=["post"])
    def deploy(self, request, uuid=None):
        template = self.get_object()
        serializer = DeployTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        vm, job = create_vm_from_template(
            template, project=data["project"], name=data["name"], storage=data["storage"], network=data["network"],
            created_by=request.user, node=data.get("node"), cpu_count=data.get("cpu_count"), memory_mb=data.get("memory_mb"),
            disk_gb=data.get("disk_gb"), autostart=data["autostart"], idempotency_key=request.META.get("HTTP_IDEMPOTENCY_KEY", ""),
        )
        log_from_request(request, action="VM_CREATE_FROM_TEMPLATE", resource_type="VirtualMachine", resource_id=str(vm.uuid), organization=vm.organization)
        return Response({"id": str(vm.uuid), "status": vm.status, "job_id": str(job.uuid) if job else None}, status=201)
