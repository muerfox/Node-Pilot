from __future__ import annotations

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FileUploadParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import log_from_request
from apps.common.permissions import HasResourcePermission
from apps.common.viewsets import OrganizationScopedModelViewSet
from apps.images import storage_backend
from apps.images.models import Image, ImageStatus, ImageUploadSession, UploadStatus
from apps.images.serializers import ImageSerializer, ImageUploadSessionSerializer, InitiateUploadSerializer
from apps.nodes.auth import AgentTokenAuthentication
from apps.nodes.views import IsAgent


class ImageViewSet(OrganizationScopedModelViewSet):
    queryset = Image.objects.select_related("storage").all()
    serializer_class = ImageSerializer
    permission_map = {
        "list": "image.view", "retrieve": "image.view",
        "destroy": "image.delete", "download": "image.view",
    }
    http_method_names = ["get", "delete", "head", "options"]  # writes only happen via the upload session flow
    filterset_fields = ["type", "status", "storage"]
    search_fields = ["name", "version"]

    def destroy(self, request, *args, **kwargs):
        image = self.get_object()
        storage_backend.delete_image_file(image)
        log_from_request(request, action="IMAGE_DELETE", resource_type="Image", resource_id=str(image.uuid), organization=image.organization)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def download(self, request, uuid=None):
        image = self.get_object()
        if image.status != ImageStatus.READY:
            return Response({"error": {"code": "IMAGE_NOT_READY", "message": "Image upload is not complete.", "details": {}}}, status=409)
        path = storage_backend.final_path(image)
        response = FileResponse(open(path, "rb"), as_attachment=True, filename=f"{image.name}.{image.format or 'img'}")
        return response


class AgentImageDownloadView(APIView):
    """GET /api/v1/agent/images/{uuid}/download/ -- an agent fetches an
    image's bytes to seed a new VM disk from it (template deployment
    with a base image, section 16). Agent-token authenticated only, and
    scoped to the requesting agent's own organization -- images are
    never public, so this must not let one org's agent fetch another
    org's private image by UUID. A 404 (not 403) for a cross-tenant hit
    so existence of the image isn't leaked either."""

    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAgent]

    def get(self, request, uuid):
        image = get_object_or_404(Image, uuid=uuid)
        if image.organization_id != request.agent.node.organization_id:
            raise Http404()
        if image.status != ImageStatus.READY:
            return Response({"error": {"code": "IMAGE_NOT_READY", "message": "Image upload is not complete.", "details": {}}}, status=409)
        path = storage_backend.final_path(image)
        response = FileResponse(open(path, "rb"))
        response["X-Image-Sha256"] = image.sha256
        response["X-Image-Format"] = image.format
        return response


class IsAgentOrHasImageView(BasePermission):
    def has_permission(self, request, view) -> bool:
        if getattr(request, "agent", None) is not None:
            return True
        if not (request.user and request.user.is_authenticated):
            return False
        from apps.permissions.policies import has_permission

        image = view.get_object() if hasattr(view, "get_object") else None
        organization = getattr(image, "organization", None)
        return has_permission(request.user, organization, "image.view")


class InitiateUploadView(APIView):
    """POST /api/v1/images/uploads/ -- begin a resumable/chunked image
    upload (section 15). Returns the session id used by ChunkUploadView."""

    permission_classes = [IsAuthenticated, HasResourcePermission]
    required_permission = "image.upload"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "image_upload"

    def get_organization(self):
        storage_id = self.request.data.get("storage")
        if not storage_id:
            return None
        from apps.storage.models import StoragePool

        pool = StoragePool.objects.filter(uuid=storage_id).select_related("node__organization").first()
        return pool.node.organization if pool else None

    def post(self, request):
        serializer = InitiateUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        storage = data["storage"]

        image = Image.objects.create(
            organization=storage.node.organization, storage=storage, name=data["name"], version=data["version"],
            type=data["type"], format=data.get("format") or data["type"].lower(), status=ImageStatus.UPLOADING,
        )
        session = ImageUploadSession.objects.create(
            image=image, created_by=request.user, total_size_bytes=data["total_size_bytes"], expected_sha256=data["expected_sha256"],
        )
        log_from_request(request, action="IMAGE_UPLOAD_INITIATE", resource_type="Image", resource_id=str(image.uuid), organization=image.organization)
        return Response(ImageUploadSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class ChunkUploadView(APIView):
    """PUT /api/v1/images/uploads/{uuid}/chunk/?index=N -- streams one
    chunk straight to disk; the request body is never buffered whole in
    memory (DRF's FileUploadParser + UploadedFile.chunks())."""

    permission_classes = [IsAuthenticated]
    parser_classes = [FileUploadParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "image_upload"

    def put(self, request, uuid):
        session = _get_session(uuid, request.user)
        if session.status != UploadStatus.UPLOADING:
            return Response({"error": {"code": "UPLOAD_NOT_ACTIVE", "message": "Session is not accepting chunks.", "details": {}}}, status=409)

        index = int(request.query_params.get("index", session.next_chunk_index))
        uploaded_file = request.data.get("file") or next(iter(request.data.values()), None)
        if uploaded_file is None:
            return Response({"error": {"code": "VALIDATION_FAILED", "message": "No file body provided.", "details": {}}}, status=400)

        written = storage_backend.write_chunk(session, index, uploaded_file)
        return Response({"received_bytes": session.received_bytes, "next_chunk_index": session.next_chunk_index, "chunk_bytes": written})


class FinalizeUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        session = _get_session(uuid, request.user)
        try:
            checksum, size = storage_backend.finalize_upload(session)
        except Exception as exc:
            session.status = UploadStatus.FAILED
            session.error = str(exc)
            session.save(update_fields=["status", "error"])
            session.image.status = ImageStatus.FAILED
            session.image.save(update_fields=["status"])
            raise

        session.status = UploadStatus.COMPLETED
        session.save(update_fields=["status"])
        image = session.image
        image.sha256 = checksum
        image.size_bytes = size
        image.status = ImageStatus.READY
        image.save(update_fields=["sha256", "size_bytes", "status"])

        log_from_request(request, action="IMAGE_UPLOAD_COMPLETE", resource_type="Image", resource_id=str(image.uuid), organization=image.organization)
        return Response(ImageSerializer(image).data)


class AbortUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, uuid):
        session = _get_session(uuid, request.user)
        storage_backend.abort_upload(session)
        session.status = UploadStatus.ABORTED
        session.save(update_fields=["status"])
        session.image.status = ImageStatus.FAILED
        session.image.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)


def _get_session(uuid, user) -> ImageUploadSession:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(ImageUploadSession, uuid=uuid, created_by=user)
