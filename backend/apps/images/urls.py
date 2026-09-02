from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.images.views import AbortUploadView, AgentImageDownloadView, ChunkUploadView, FinalizeUploadView, ImageViewSet, InitiateUploadView

router = DefaultRouter()
router.register("images", ImageViewSet, basename="image")

urlpatterns = [
    path("images/uploads/", InitiateUploadView.as_view(), name="image-upload-initiate"),
    path("images/uploads/<uuid:uuid>/chunk/", ChunkUploadView.as_view(), name="image-upload-chunk"),
    path("images/uploads/<uuid:uuid>/finalize/", FinalizeUploadView.as_view(), name="image-upload-finalize"),
    path("images/uploads/<uuid:uuid>/abort/", AbortUploadView.as_view(), name="image-upload-abort"),
    path("agent/images/<uuid:uuid>/download/", AgentImageDownloadView.as_view(), name="agent-image-download"),
] + router.urls
